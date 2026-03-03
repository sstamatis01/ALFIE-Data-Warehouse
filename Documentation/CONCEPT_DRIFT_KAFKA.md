# Concept Drift Kafka Events

## Overview

Concept drift runs **after** AutoML: it uses the **drift** split (15%) of the dataset and the trained model to detect drift (ADWIN) and retrain adaptively (AutoGluon). The retrained model is uploaded to the Data Warehouse as a new version.

- **Trigger topic:** `concept-drift-trigger-events` (produced by Agentic Core or orchestration)
- **Complete topic:** `concept-drift-complete-events` (produced by the concept-drift consumer)

The dataset must have the automatic train/test/drift split (i.e. enough samples so that the DW created `train/`, `test/`, `drift/` in MinIO). The consumer downloads only the drift split via `.../download?split=drift`.

---

## Automatic 70-15-15 split (Data Warehouse)

The Data Warehouse creates the train/test/drift split **automatically** when:

1. **Tabular data:** The uploaded file (or folder) is CSV or Excel and the dataset is large enough: `num_samples > (num_features + 1) * 10`.
2. **Versioning:** The upload requests a second version for the split (e.g. v2). The API reserves v1 for the original and v2 for the split.

**Split ratios:** 70% train, 15% test, 15% drift (defined in `app/services/file_service.py`: `SPLIT_TRAIN_RATIO`, `SPLIT_TEST_RATIO`, `SPLIT_DRIFT_RATIO`).

**Where it’s stored:** Original is always in **v1**. When a split is created, it is stored under **v2** in MinIO with subfolders `train/`, `test/`, and `drift/`. The DW emits Kafka `dataset-events` for the **v2** version so the rest of the pipeline (bias, AutoML, XAI) runs on the split data. The concept-drift consumer uses only the **drift** portion via `GET .../download?split=drift`.

---

## concept-drift-trigger (payload)

Producers (e.g. Agentic Core) send to `concept-drift-trigger-events`:

```json
{
  "task_id": "concept_drift_task_<id>",
  "event_type": "concept-drift-trigger",
  "timestamp": "2025-02-10T12:00:00.000000Z",
  "input": {
    "user_id": "user123",
    "dataset_id": "dataset456",
    "dataset_version": "v1",
    "model_id": "automl_model_1",
    "model_version": "v1",
    "target_column_name": "target",
    "window_size": 100
  }
}
```

| Field | Required | Description |
|-------|----------|-------------|
| task_id | Yes | Correlation ID for completion event |
| input.user_id | Yes | Owner of dataset and model |
| input.dataset_id | Yes | Dataset with train/test/drift split |
| input.dataset_version | No | Default `v1` |
| input.model_id | Yes | Model produced by AutoML to adapt |
| input.model_version | No | Default `v1` |
| input.target_column_name | Yes | Target column for prediction |
| input.window_size | No | ADWIN retrain window size (default 100) |

---

## concept-drift-complete (payload)

The concept-drift consumer sends to `concept-drift-complete-events`:

**Success:**

```json
{
  "task_id": "concept_drift_task_<id>",
  "event_type": "concept-drift-complete",
  "timestamp": "2025-02-10T12:05:00.000000Z",
  "output": {
    "user_id": "user123",
    "model_id": "automl_model_1",
    "model_version": "v2",
    "dataset_id": "dataset456",
    "dataset_version": "v1",
    "drift_metrics": {
      "cumulative_accuracy": 0.92,
      "final_accuracy": 0.91,
      "f1_score": 0.90,
      "precision": 0.89,
      "recall": 0.88,
      "total_drifts": 2,
      "total_retrain_time_seconds": 45.2,
      "total_runtime_seconds": 120.5
    }
  },
  "failure": null
}
```

**Failure:**

```json
{
  "task_id": "concept_drift_task_<id>",
  "event_type": "concept-drift-complete",
  "timestamp": "2025-02-10T12:05:00.000000Z",
  "output": null,
  "failure": {
    "error_type": "ConceptDriftError",
    "error_message": "Drift split empty or too small"
  }
}
```

---

## Dataset download and the 70-15-15 split

- **Full dataset (no change):** `GET /datasets/{user_id}/{dataset_id}/version/{version}/download` returns all files (train + test + drift when present) in one ZIP. Existing consumers (AutoML, bias, etc.) keep working.
- **By split:** `GET .../download?split=drift` (or `train` or `test`) returns only that subset when the dataset has a split. Use this for the concept-drift consumer so it only downloads the 15% drift portion.
- The split is created automatically by the DW on upload when the dataset is large enough and a second version (v2) is used; see [Automatic 70-15-15 split (Data Warehouse)](#automatic-70-15-15-split-data-warehouse) above.

---

## Consumer

- **Script:** `kafka_concept_drift_consumer_example.py`
- **Docker service:** `concept-drift-consumer` in `docker-compose.yml`
- **Dependencies:** `river`, `autogluon.tabular`, `pandas`, `scikit-learn`, `aiokafka`, `requests`, `catboost`, `lightgbm`, `xgboost`, `torch`, `fastai` (needed to load saved predictors that use these backends)

The consumer downloads the drift split, loads the model from the DW, runs `monitor_drift_and_retrain` (ADWIN + AutoGluon retrain), zips the new model, uploads it via `POST /ai-models/upload/folder/{user_id}`, then sends `concept-drift-complete`.

---

## Running the consumer outside Docker (Anaconda)

If the Docker image fails to provide `pkg_resources` (used by AutoGluon), run the concept-drift consumer **outside Docker** in an Anaconda (or conda) environment where setuptools is always available:

1. **Create and activate an env (Python 3.11 recommended):**
   ```bash
   conda create -n concept-drift python=3.11 -y
   conda activate concept-drift
   ```

2. **Install dependencies from the project root:**
   ```bash
   cd /path/to/ALFIE-Data-Warehouse-git
   pip install -r requirements.txt
   ```
   Or install only what the consumer needs (include backends so saved AutoML predictors can be loaded):
   ```bash
   pip install aiokafka requests pandas river "autogluon.tabular>=1.0.0,<1.2" python-dotenv setuptools catboost lightgbm xgboost torch fastai
   ```

3. **Set environment variables** so the consumer can reach Kafka and the Data Warehouse API (e.g. from `.env` or export):
   - `KAFKA_BOOTSTRAP_SERVERS` (e.g. `localhost:9092` or your Kafka address)
   - `API_BASE` or `DW_HOST`/`DW_PORT` (e.g. `http://localhost:8000`)

4. **Run the consumer:**
   ```bash
   python kafka_concept_drift_consumer_example.py
   ```

Keep the rest of the stack (API, Kafka, bias, AutoML, orchestrator) running in Docker; only the concept-drift consumer runs on the host with Anaconda.

---

## Troubleshooting (running outside Docker)

### PyTorch DLL error on Windows (WinError 1114 / c10.dll)

If the saved predictor includes a neural network model, loading it requires PyTorch. On Windows you may see:

```text
OSError: [WinError 1114] A dynamic link library (DLL) initialization routine failed. Error loading "...\torch\lib\c10.dll" or one of its dependencies.
```

**Try in this order:**

1. **Install Microsoft Visual C++ Redistributable**  
   Download and install the latest [Visual C++ Redistributable for Visual Studio](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist) (e.g. “x64”) and restart.

2. **Use the official PyTorch CPU-only build** (often more reliable on Windows):
   ```bash
   pip uninstall torch -y
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   ```

3. **Run the consumer in a Linux environment**  
   Use WSL2, a Linux VM, or the Docker image (if `pkg_resources` is fixed there). PyTorch tends to work without DLL issues on Linux.

### NumPy BitGenerator error when loading predictor

If you see:

```text
ValueError: <class 'numpy.random._mt19937.MT19937'> is not a known BitGenerator module.
```

the model was saved with **NumPy 2.x** but the concept-drift stack (AutoGluon 1.1.x, pandas, river, scikit-learn, scipy) **requires NumPy 1.x**. You cannot upgrade the concept-drift env to NumPy 2 without upgrading the whole stack (AutoGluon, pandas, etc.), which may not support it yet.

**Fix (pick one):**

- **Option A – Fix the training side (recommended if you control it):**  
  In the environment that **trains and saves** the predictor, use **NumPy 1.x** (e.g. `numpy>=1.26,<2`) when saving. Then the concept-drift env can keep NumPy 1.x and load the model without BitGenerator errors.

- **Option B – Align concept-drift env with training (if the model is already saved with NumPy 2):**  
  The saved model was created with **AutoGluon 1.4, Python 3.12, NumPy 2**. Use a dedicated env that matches that so the pickle loads correctly:

  1. Create a new env with Python 3.12 and NumPy 2–compatible packages:
     ```bash
     conda create -n concept-drift-py312 python=3.12 -y
     conda activate concept-drift-py312
     ```
  2. Install NumPy 2 and AutoGluon 1.4 first, then the rest (let pip resolve):
     ```bash
     pip install "numpy>=2.0"
     pip install "autogluon.tabular>=1.4,<1.5"
     pip install aiokafka requests pandas river python-dotenv setuptools catboost lightgbm xgboost torch
     ```
  3. Run the concept-drift consumer or `AutoCDD.py` in this env. You may need to upgrade `pandas`, `scikit-learn`, `scipy`, `river` to versions that support NumPy 2 if pip reports conflicts.

  This is a **NumPy major-version** issue (pickle format), not a Python version issue, but matching Python 3.12 and AutoGluon 1.4 avoids version-mismatch warnings and keeps load/save compatible.
