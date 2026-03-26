#!/usr/bin/env python3
"""
Kafka Consumer for Concept Drift Trigger Events

Listens to concept-drift-trigger-events. On trigger:
- Downloads the drift split of the dataset (15%) from the Data Warehouse
- Downloads the trained model (from AutoML) from the Data Warehouse
- Runs concept drift detection (ADWIN) and adaptive retraining (AutoGluon)
- If drift is detected: retrains, uploads the new model to the Data Warehouse, sends concept-drift-complete with new model version
- If no drift is detected: skips upload and sends concept-drift-complete with success and message "No concept drift detected"

Requires: river, autogluon.tabular, pandas, requests, aiokafka.
Dataset must have train/test/drift split (use split=drift when downloading).
"""

import os
import io
import shutil
import time
import uuid
import asyncio
import json
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from collections import deque

# Required by AutoGluon during TabularPredictor.load; provided by setuptools (in requirements.txt / Dockerfile).
try:
    import pkg_resources  # noqa: F401
except ModuleNotFoundError:
    raise RuntimeError(
        "pkg_resources not found. Rebuild the Docker image so setuptools is installed: "
        "requirements.txt includes setuptools>=65.0.0 and the Dockerfile reinstalls it after other deps. "
        "Run: docker compose build --no-cache concept-drift-consumer"
    ) from None

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import numpy as np
import requests
import pandas as pd
from dotenv import load_dotenv, find_dotenv
from river.drift import ADWIN
from autogluon.tabular import TabularPredictor
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score, recall_score,
    mean_absolute_error, mean_squared_error, r2_score
)
import matplotlib.pyplot as plt


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("kafka_concept_drift_consumer")

load_dotenv(find_dotenv())

# Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_DRIFT_TRIGGER_TOPIC = os.getenv("KAFKA_CONCEPT_DRIFT_TRIGGER_TOPIC", "concept-drift-trigger-events")
KAFKA_DRIFT_COMPLETE_TOPIC = os.getenv("KAFKA_CONCEPT_DRIFT_COMPLETE_TOPIC", "concept-drift-complete-events")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONCEPT_DRIFT_CONSUMER_GROUP", "concept-drift-consumer")

# Data Warehouse API
DW_HOST = os.getenv("DW_HOST", "localhost")
DW_PORT = os.getenv("DW_PORT", "8000")
API_BASE = os.getenv("API_BASE") or f"http://{DW_HOST}:{DW_PORT}"

logger.info(f"Configuration: API_BASE={API_BASE}, trigger_topic={KAFKA_DRIFT_TRIGGER_TOPIC}, complete_topic={KAFKA_DRIFT_COMPLETE_TOPIC}")


def download_drift_dataset(user_id: str, dataset_id: str, version: str) -> pd.DataFrame:
    """Download the drift split of the dataset (ZIP) and load first CSV as DataFrame."""
    url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/version/{version}/download?split=drift"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    zip_bytes = r.content
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        names = [n for n in z.namelist() if n.endswith(".csv") and not n.startswith("__")]
        if not names:
            raise ValueError("No CSV file in drift split ZIP")
        with z.open(names[0]) as f:
            return pd.read_csv(io.BytesIO(f.read()))


def download_model_folder(user_id: str, model_id: str, model_version: str, extract_to: str) -> str:
    """Download model ZIP from DW and extract to extract_to. Returns path to extracted folder (root of model)."""
    url = f"{API_BASE}/ai-models/{user_id}/{model_id}/download?version={model_version}"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content), "r") as z:
        z.extractall(extract_to)
    return extract_to


def find_autogluon_model_dir(extract_to: str) -> str:
    """
    Find the directory that contains predictor.pkl (AutoGluon save format).
    DW zip may have: predictor.pkl at root, or a subfolder (e.g. AgAutogluon/predictor.pkl),
    or a single inner model.zip that must be extracted first.
    Returns the path to the directory containing predictor.pkl for TabularPredictor.load().
    """
    # First pass: look for predictor.pkl anywhere under extract_to
    for root, _dirs, files in os.walk(extract_to):
        if "predictor.pkl" in files:
            return root
    # Second pass: if there is a single .zip (nested model), extract and search again
    for root, _dirs, files in os.walk(extract_to):
        zips = [f for f in files if f.lower().endswith(".zip")]
        for z in zips:
            zip_path = os.path.join(root, z)
            inner_dir = os.path.join(root, "inner_model")
            os.makedirs(inner_dir, exist_ok=True)
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(inner_dir)
                for r2, _d2, f2 in os.walk(inner_dir):
                    if "predictor.pkl" in f2:
                        return r2
            except (zipfile.BadZipFile, OSError):
                continue
    raise FileNotFoundError(
        f"No predictor.pkl found under {extract_to}. "
        "Expected AutoGluon TabularPredictor save (predictor.pkl) in the model zip from the Data Warehouse."
    )


def predict_autogluon(predictor, row, feature_cols):
    """Single-row prediction with AutoGluon TabularPredictor."""
    X = pd.DataFrame([row[feature_cols]])
    return predictor.predict(X).iloc[0]


def monitor_drift_and_retrain(df, predictor, feature_cols, target_col, retrain_path: str, window_size: int = 150,
    delta=0.1,
    clock=1,
    batch_predict_size=512,
    retrain_presets="medium_quality_faster_train",
    min_samples_before_detection=50,
    cooldown_samples=50,
    verbose=True):
    """
    Monitor drift with ADWIN and retrain AutoGluon on a sliding window.

    Classification:
        ADWIN monitors 1 - P(true_class)

    Regression:
        ADWIN monitors absolute error

    Parameters
    ----------
    df : pd.DataFrame
        Drift stream data.
    predictor : TabularPredictor
        Already-trained AutoGluon predictor.
    feature_cols : list[str]
        Input feature columns.
    target_col : str
        Target column.
    window_size : int
        Number of recent rows used for retraining when drift is detected.
    delta : float
        ADWIN sensitivity parameter. Larger => easier to trigger.
    clock : int
        ADWIN check frequency. 1 = every sample.
    batch_predict_size : int
        Batch size for predictor.predict / predict_proba.
    retrain_presets : str
        AutoGluon presets used during retraining.
    min_samples_before_detection : int
        Ignore detections until at least this many samples have been processed.
    cooldown_samples : int
        After drift detection, ignore further detections for this many samples.
    retrain_path : str
        Root folder where retrained models are saved.
    verbose : bool
        Print diagnostics and drift events.
    """

    # --------------------------
    # 1) Detect problem type
    # --------------------------
    def infer_problem_type(df_: pd.DataFrame, target: str, pred) -> str:
        pt = getattr(pred, "problem_type", None)
        if isinstance(pt, str) and pt:
            return pt.lower()

        y = df_[target]
        if pd.api.types.is_numeric_dtype(y):
            nunique = y.nunique(dropna=True)
            n = len(y)
            if nunique <= 20 or (n > 0 and (nunique / n) < 0.05):
                return "multiclass"
            return "regression"
        return "multiclass"


    def normalize_label(v):
        if pd.isna(v):
            return "NA"
        if isinstance(v, (float, np.floating)) and float(v).is_integer():
            v = int(v)
        return str(v).strip()


    def coerce_classification_labels(y_true_ser, y_pred_ser):
        y_true_labels = y_true_ser.map(normalize_label)
        y_pred_labels = y_pred_ser.map(normalize_label)
        return y_true_labels, y_pred_labels


    if df is None or df.empty:
        raise ValueError("Input df is empty.")

    missing_features = [c for c in feature_cols if c not in df.columns]
    if missing_features:
        raise ValueError(f"Missing feature columns in df: {missing_features}")

    if target_col not in df.columns:
        raise ValueError(f"Target column '{target_col}' not found in df.")

    problem_type = infer_problem_type(df, target_col, predictor)
    is_regression = (problem_type == "regression") or ("regress" in str(problem_type).lower())

    n_rows = len(df)
    logger.info(
        "[Drift] Starting monitoring: rows=%d, target=%s, window_size=%d, retrain_path=%s",
        n_rows,
        target_col,
        window_size,
        retrain_path,
    )

    # --------------------------
    # 2) Drift detector
    # --------------------------
    adwin = ADWIN(delta=delta, clock=clock)
    window_rows = deque(maxlen=window_size)
    events = []
    error_stream = []
    y_true_all, y_pred_all = [], []
    window_y_true = deque(maxlen=window_size)
    window_y_pred = deque(maxlen=window_size)
    total_retrain_time = 0.0
    start_time = __import__("time").time()
    log_interval = max(1, n_rows // 10)  # log progress ~10 times over the run
    samples_seen = 0
    cooldown_until = -1

    # --------------------------
    # 4) Main monitoring loop
    # --------------------------
    for batch_start in range(0, n_rows, batch_predict_size):
        batch_end = min(batch_start + batch_predict_size, n_rows)
        batch_df = df.iloc[batch_start:batch_end].copy()
        X_batch = batch_df[feature_cols]

        batch_preds = predictor.predict(X_batch)

        if not is_regression:
            batch_proba = predictor.predict_proba(X_batch).copy()
            batch_proba.columns = [normalize_label(c) for c in batch_proba.columns]
        else:
            batch_proba = None

        for offset, (_, row) in enumerate(batch_df.iterrows()):
            i = batch_start + offset
            y_true = row[target_col]
            y_pred = batch_preds.iloc[offset]

            # -------------------------
            # Build monitored signal
            # -------------------------
            if is_regression:
                y_true_num = pd.to_numeric(pd.Series([y_true]), errors="coerce").iloc[0]
                y_pred_num = pd.to_numeric(pd.Series([y_pred]), errors="coerce").iloc[0]

                if pd.isna(y_true_num) or pd.isna(y_pred_num):
                    error = 0.0
                else:
                    error = float(abs(y_pred_num - y_true_num))
            else:
                y_true_key = normalize_label(y_true)
                y_pred_key = normalize_label(y_pred)

                if y_true_key in batch_proba.columns:
                    true_class_prob = float(batch_proba.iloc[offset][y_true_key])
                    error = 1.0 - true_class_prob
                else:
                    error = 0.0 if y_pred_key == y_true_key else 1.0

            error_stream.append(error)

            # -------------------------
            # Store for metrics/retrain
            # -------------------------
            y_true_all.append(y_true)
            y_pred_all.append(y_pred)

            window_y_true.append(y_true)
            window_y_pred.append(y_pred)
            window_rows.append(row)

            samples_seen += 1
            elapsed = __import__("time").time() - start_time

            if (i + 1) % log_interval == 0 or i == 0:
                correct_so_far = sum(1 for a, b in zip(y_true_all, y_pred_all) if a == b)
                logger.info(
                    "[Drift] Progress row %d/%d, cumulative_accuracy=%.4f, window_fill=%d",
                    i + 1,
                    n_rows,
                    correct_so_far / len(y_true_all) if y_true_all else 0,
                    len(window_rows),
                )

            # -------------------------
            # Detection logic
            # -------------------------
            adwin.update(error)

            detection_allowed = (
                    samples_seen >= min_samples_before_detection and
                    i > cooldown_until and
                    len(window_rows) >= min_samples_before_detection
            )

            if detection_allowed and adwin.drift_detected:
                if verbose:
                    logger.info(
                        "[Drift] Concept drift DETECTED at index %d. Retraining on last %d samples at path=%s",
                        i,
                        len(window_rows),
                        retrain_path,)

                window_df = pd.DataFrame(list(window_rows))
                retrain_start = __import__("time").time()

                unique_path = os.path.join(
                    retrain_path,
                    f"retrain_{i}_{uuid.uuid4().hex[:8]}"
                )

                fit_kwargs = {}
                if is_regression:
                    fit_kwargs["problem_type"] = "regression"
                elif problem_type == "binary":
                    fit_kwargs["problem_type"] = "binary"
                else:
                    fit_kwargs["problem_type"] = "multiclass"

                predictor = TabularPredictor(
                    label=target_col,
                    path=unique_path,
                    **fit_kwargs
                ).fit(
                    train_data=window_df,
                    presets=retrain_presets
                )

                retrain_time = __import__("time").time() - retrain_start
                total_retrain_time += retrain_time

                events.append({
                    "index": i,
                    "elapsed_seconds": elapsed,
                    "window_size": len(window_rows),
                    "retrain_time_seconds": retrain_time,
                    "mean_error_so_far": float(np.mean(error_stream)) if error_stream else np.nan,
                })

                if verbose:
                    logger.info("[Drift] Retraining took %s seconds.", {retrain_time:.4})

                # Reset detector after confirmed drift
                adwin = ADWIN(delta=delta, clock=clock)

                # Cooldown to avoid repeated detections from same change point
                cooldown_until = i + cooldown_samples

                # Confirm that fit() wrote to retrain_path (and list contents)
                try:
                    contents = []
                    for _root, _dirs, files in os.walk(retrain_path):
                        contents.extend(os.path.join(os.path.relpath(_root, retrain_path), f) for f in files)
                    logger.info("[Drift] After retrain: path=%s has %d files: %s", retrain_path, len(contents),
                                contents[:20])
                except Exception as e:
                    logger.warning("[Drift] Could not list retrain_path after fit: %s", e)

    # -------------------------
    # Signal diagnostics
    # -------------------------
    if verbose and error_stream:
        error_arr = np.asarray(error_stream, dtype=float)
        print("\n--- Drift Signal Diagnostics ---")
        print(f"Mean error: {error_arr.mean():.4f}")
        print(f"Std error: {error_arr.std():.4f}")

        mid = len(error_arr) // 2
        if mid > 0:
            print(f"First half mean error: {error_arr[:mid].mean():.4f}")
            print(f"Second half mean error: {error_arr[mid:].mean():.4f}")

        q = len(error_arr) // 4
        if q > 0:
            print(f"Q1 mean error: {error_arr[:q].mean():.4f}")
            print(f"Q2 mean error: {error_arr[q:2 * q].mean():.4f}")
            print(f"Q3 mean error: {error_arr[2 * q:3 * q].mean():.4f}")
            print(f"Q4 mean error: {error_arr[3 * q:].mean():.4f}")

        seg_edges = np.linspace(0, len(error_arr), 12, dtype=int)
        print("\n--- Segment mean errors ---")
        for s in range(11):
            a, b = seg_edges[s], seg_edges[s + 1]
            if b > a:
                print(f"Segment {s}: {error_arr[a:b].mean():.4f}")

    # Summary: whether any retrain happened (if not, retrain_path stays empty and upload will fail)
    drift_log = pd.DataFrame(events)
    total_runtime = __import__("time").time() - start_time
    total_drifts = len(events)
    n_drifts = len(events)
    total_count = len(y_true_all)
    correct_count = sum(1 for a, b in zip(y_true_all, y_pred_all) if a == b)
    try:
        retrain_files = []
        for root, _d, files in os.walk(retrain_path):
            retrain_files.extend(os.path.join(root, f) for f in files)
        logger.info(
            "[Drift] Monitoring complete. Drifts detected=%d, total retrain_time=%.2fs, retrain_path has %d files",
            n_drifts,
            total_retrain_time,
            len(retrain_files),
        )
        if n_drifts == 0:
            logger.info(
                "[Drift] No drift was detected during this run; no retrain occurred. "
                "Consumer will send success without uploading a new model."
            )
    except Exception as e:
        logger.warning("[Drift] Could not list retrain_path at end: %s", e)

    # --------------------------
    # 5) Compute correct metrics
    # --------------------------
    if not y_true_all:
        if is_regression:
            metrics = {
                "problem_type": "regression",
                "mae": float("nan"),
                "mse": float("nan"),
                "rmse": float("nan"),
                "r2": float("nan"),
                "final_window_mae": float("nan"),
                "total_drifts": total_drifts,
                "total_retrain_time_seconds": total_retrain_time,
                "total_runtime_seconds": total_runtime,
            }
        else:
            metrics = {
                "problem_type": "classification",
                "cumulative_accuracy": float("nan"),
                "final_accuracy": float("nan"),
                "final_window_accuracy": float("nan"),
                "f1_score": float("nan"),
                "precision": float("nan"),
                "recall": float("nan"),
                "total_drifts": total_drifts,
                "total_retrain_time_seconds": total_retrain_time,
                "total_runtime_seconds": total_runtime,
            }
        return predictor, drift_log, metrics

    if is_regression:
        y_true_arr = np.asarray(pd.to_numeric(pd.Series(y_true_all), errors="coerce"))
        y_pred_arr = np.asarray(pd.to_numeric(pd.Series(y_pred_all), errors="coerce"))

        valid_mask = ~np.isnan(y_true_arr) & ~np.isnan(y_pred_arr)
        y_true_arr = y_true_arr[valid_mask]
        y_pred_arr = y_pred_arr[valid_mask]

        if len(y_true_arr) == 0:
            mae = mse = rmse = r2 = float("nan")
        else:
            mae = mean_absolute_error(y_true_arr, y_pred_arr)
            mse = mean_squared_error(y_true_arr, y_pred_arr)
            rmse = float(np.sqrt(mse))
            r2 = r2_score(y_true_arr, y_pred_arr)

        if window_y_true:
            wy_true = np.asarray(pd.to_numeric(pd.Series(list(window_y_true)), errors="coerce"))
            wy_pred = np.asarray(pd.to_numeric(pd.Series(list(window_y_pred)), errors="coerce"))
            valid_mask = ~np.isnan(wy_true) & ~np.isnan(wy_pred)
            wy_true = wy_true[valid_mask]
            wy_pred = wy_pred[valid_mask]
            final_window_mae = mean_absolute_error(wy_true, wy_pred) if len(wy_true) else float("nan")
        else:
            final_window_mae = float("nan")

        metrics = {
            "problem_type": "regression",
            "mae": mae,
            "mse": mse,
            "rmse": rmse,
            "r2": r2,
            "final_window_mae": final_window_mae,
            "total_drifts": total_drifts,
            "total_retrain_time_seconds": total_retrain_time,
            "total_runtime_seconds": total_runtime,
        }

    else:
        # Classification problem
        y_true_ser = pd.Series(y_true_all)
        y_pred_ser = pd.Series(y_pred_all)

        y_true_labels, y_pred_labels = coerce_classification_labels(y_true_ser, y_pred_ser)

        final_accuracy = accuracy_score(y_true_labels, y_pred_labels)
        f1 = f1_score(y_true_labels, y_pred_labels, average="weighted")
        precision = precision_score(y_true_labels, y_pred_labels, average="weighted", zero_division=0)
        recall = recall_score(y_true_labels, y_pred_labels, average="weighted", zero_division=0)
        cumulative_accuracy = float((y_true_labels == y_pred_labels).mean())

        if window_y_true:
            wy_true = pd.Series(list(window_y_true))
            wy_pred = pd.Series(list(window_y_pred))
            wy_true_labels, wy_pred_labels = coerce_classification_labels(wy_true, wy_pred)
            final_window_accuracy = accuracy_score(wy_true_labels, wy_pred_labels)
        else:
            final_window_accuracy = float("nan")

        metrics = {
            "problem_type": "classification",
            "cumulative_accuracy": cumulative_accuracy,
            "final_accuracy": final_accuracy,
            "final_window_accuracy": final_window_accuracy,
            "f1_score": f1,
            "precision": precision,
            "recall": recall,
            "total_drifts": total_drifts,
            "total_retrain_time_seconds": total_retrain_time,
            "total_runtime_seconds": total_runtime,
        }

    return predictor, drift_log, metrics


def infer_task_type(df, target_col):
    y = df[target_col]
    if pd.api.types.is_numeric_dtype(y):
        nunique = y.nunique(dropna=True)
        if nunique <= 20:
            return "classification"
        return "regression"
    return "classification"


def drift_induction(
    data,
    drift_strength=0.3,
    random_state=None,
    target_col=None,
    task="auto",
    n_drifts=10
):
    """
    Inject exactly `n_drifts` abrupt drifts by splitting the data into `n_drifts + 1`
    consecutive segments and applying a different transformation to each segment.

    Notes:
    - Guarantees 10 *induced change points* when there are enough rows.
    - Does NOT guarantee that a drift detector will detect all of them.
    - For classification, target_col is required.
    - For regression, target drift is optional but supported if target_col is provided.

    Parameters
    ----------
    data : pd.DataFrame or array-like
        Input data.
    drift_strength : float
        Base intensity of the drift.
    random_state : int or None
        Random seed.
    target_col : str or None
        Target column name for supervised datasets.
    task : {"auto", "classification", "regression"}
        Task type.
    n_drifts : int
        Number of drift points to inject.

    Returns
    -------
    pd.DataFrame or np.ndarray
        Drifted dataset of the same shape as input.
    """
    if random_state is not None:
        np.random.seed(random_state)

    is_dataframe = isinstance(data, pd.DataFrame)

    if not is_dataframe:
        arr = np.asarray(data).copy()
        if arr.ndim != 2:
            raise ValueError("NumPy input must be 2D.")
        if len(arr) < (n_drifts + 1):
            raise ValueError(
                f"Need at least {n_drifts + 1} rows to induce {n_drifts} drifts, got {len(arr)}."
            )

        # NumPy path: treat as regression-style numeric data only
        if not np.issubdtype(arr.dtype, np.number):
            raise TypeError("NumPy input must be numeric.")

        segment_edges = np.linspace(0, len(arr), n_drifts + 2, dtype=int)
        drifted = arr.copy()

        for seg_id in range(n_drifts + 1):
            start = segment_edges[seg_id]
            end = segment_edges[seg_id + 1]
            if start >= end:
                continue

            # Keep first segment untouched as baseline
            if seg_id == 0:
                continue

            segment = drifted[start:end].copy()

            seg_strength = drift_strength * seg_id

            # abrupt alternating regimes
            shift = seg_strength * (1 if seg_id % 2 == 1 else -1)
            scale = 1.0 + (0.8 if seg_id % 3 == 0 else -0.5)
            noise_std = max(0.05, drift_strength * 0.25)

            segment = segment * scale
            segment = segment + shift
            segment = segment + np.random.normal(0, noise_std, size=segment.shape)

            drifted[start:end] = segment

        return drifted

    # -------------------------
    # DataFrame path
    # -------------------------
    df = data.copy()

    if len(df) < (n_drifts + 1):
        raise ValueError(
            f"Need at least {n_drifts + 1} rows to induce {n_drifts} drifts, got {len(df)}."
        )

    # infer task
    if task == "auto":
        if target_col is None or target_col not in df.columns:
            task = "regression"
        else:
            y = df[target_col]
            if pd.api.types.is_numeric_dtype(y):
                nunique = y.nunique(dropna=True)
                if nunique <= 20:
                    task = "classification"
                else:
                    task = "regression"
            else:
                task = "classification"

    if task == "classification" and (target_col is None or target_col not in df.columns):
        raise ValueError("For classification, target_col must be provided and exist in the DataFrame.")

    drifted = df.copy()

    numeric_cols = drifted.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = drifted.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

    if target_col is not None and target_col in numeric_cols:
        numeric_cols.remove(target_col)
    if target_col is not None and target_col in categorical_cols:
        categorical_cols.remove(target_col)

    segment_edges = np.linspace(0, len(drifted), n_drifts + 2, dtype=int)

    for seg_id in range(n_drifts + 1):
        start = segment_edges[seg_id]
        end = segment_edges[seg_id + 1]
        if start >= end:
            continue

        idx = drifted.index[start:end]

        # Keep first segment untouched as clean baseline
        if seg_id == 0:
            continue

        seg_strength = drift_strength * seg_id

        # -------------------------
        # Numeric feature drift
        # -------------------------
        if numeric_cols:
            block = drifted.loc[idx, numeric_cols].to_numpy(dtype=float)

            # abrupt alternating regimes
            shift = seg_strength * (1 if seg_id % 2 == 1 else -1)
            scale = 1.0 + (0.8 if seg_id % 3 == 0 else -0.5)
            noise_std = max(0.05, drift_strength * 0.25)

            block = block * scale
            block = block + shift
            block = block + np.random.normal(0, noise_std, size=block.shape)

            drifted.loc[idx, numeric_cols] = block

        # -------------------------
        # Categorical feature drift
        # -------------------------
        if categorical_cols:
            for col in categorical_cols:
                values = drifted.loc[idx, col].astype("object")
                unique_vals = values.dropna().unique()

                if len(unique_vals) > 1:
                    replace_frac = min(0.6, 0.15 + 0.05 * seg_id)
                    n_replace = int(len(idx) * replace_frac)

                    if n_replace > 0:
                        replace_idx = np.random.choice(idx, size=n_replace, replace=False)

                        def sample_other(v):
                            choices = [x for x in unique_vals if x != v]
                            return np.random.choice(choices) if len(choices) > 0 else v

                        drifted.loc[replace_idx, col] = drifted.loc[replace_idx, col].apply(sample_other)

        # -------------------------
        # Target drift
        # -------------------------
        if target_col is not None:
            if task == "classification":
                classes = drifted[target_col].dropna().unique()
                if len(classes) > 1:
                    # strong post-baseline label drift
                    flip_frac = min(0.7, 0.20 + 0.05 * seg_id)
                    n_flip = int(len(idx) * flip_frac)

                    if n_flip > 0:
                        flip_idx = np.random.choice(idx, size=n_flip, replace=False)

                        def sample_other_class(v):
                            choices = [c for c in classes if c != v]
                            return np.random.choice(choices) if len(choices) > 0 else v

                        drifted.loc[flip_idx, target_col] = drifted.loc[flip_idx, target_col].apply(sample_other_class)


            elif task == "regression" and pd.api.types.is_numeric_dtype(drifted[target_col]):
                target_shift = seg_strength * (1 if seg_id % 2 == 1 else -1) * 0.75
                target_noise = max(0.02, drift_strength * 0.08)
                drifted.loc[idx, target_col] = (
                        pd.to_numeric(drifted.loc[idx, target_col], errors="coerce")
                        + target_shift
                        + np.random.normal(0, target_noise, size=len(idx))
                )

    return drifted


def zip_dir(path: str) -> bytes:
    """Zip a directory and return bytes."""
    buf = io.BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(path):
            for f in files:
                abspath = os.path.join(root, f)
                arcname = os.path.relpath(abspath, path)
                # Use forward slashes in archive so API (possibly Linux) extracts correctly
                arcname = arcname.replace("\\", "/")
                z.write(abspath, arcname)
                count += 1
    if count == 0:
        logger.warning("zip_dir: no files found under %s", path)
    else:
        logger.info("zip_dir: zipped %d files from %s", count, path)
    buf.seek(0)
    return buf.getvalue()


def upload_model_to_dw(
    user_id: str,
    model_id: str,
    model_zip_bytes: bytes,
    dataset_id: str,
    dataset_version: str,
    model_type: str = "classification",
    framework: str = "other",
    description_prefix: str = "Concept drift retrained model",
) -> dict:
    """Upload retrained model (ZIP folder) to Data Warehouse. Returns created model metadata."""
    url = f"{API_BASE}/ai-models/upload/folder/{user_id}"
    # API expects File(...) under key "zip_file" and Form fields; ensure zip is non-empty and stream at 0
    if not model_zip_bytes or len(model_zip_bytes) < 22:  # minimal zip is ~22 bytes
        raise ValueError(f"Model zip is empty or too small ({len(model_zip_bytes) if model_zip_bytes else 0} bytes)")
    zip_buffer = io.BytesIO(model_zip_bytes)
    zip_buffer.seek(0)
    files = {"zip_file": ("model.zip", zip_buffer, "application/zip")}
    data = {
        "model_id": model_id,
        "name": f"{description_prefix} - {model_id}",
        "description": f"{description_prefix} (drift retrain on dataset {dataset_id} {dataset_version})",
        "framework": framework,
        "model_type": model_type,
        "training_dataset": dataset_id,
        "preserve_structure": "true",
    }
    r = requests.post(url, files=files, data=data, timeout=300)
    if not r.ok:
        try:
            err_body = r.json()
            logger.error(f"Upload model failed {r.status_code}: {err_body}")
        except Exception:
            logger.error(f"Upload model failed {r.status_code}: {r.text[:500]}")
        r.raise_for_status()
    return r.json()


async def process_drift_trigger(event: dict, producer: AIOKafkaProducer) -> None:
    """Handle one concept-drift-trigger event."""
    task_id = event.get("task_id") or event.get("event_id")
    input_obj = event.get("input", event)
    user_id = input_obj.get("user_id")
    dataset_id = input_obj.get("dataset_id")
    dataset_version = input_obj.get("dataset_version", "v1")
    model_id = input_obj.get("model_id")
    model_version = input_obj.get("model_version", "v1")
    target_column = input_obj.get("target_column_name") or input_obj.get("target_column")
    window_size = int(input_obj.get("window_size", 100))

    if not all([user_id, dataset_id, model_id]):
        logger.warning("Missing user_id, dataset_id or model_id; skipping")
        await _send_complete(producer, task_id, user_id, model_id, None, dataset_id, dataset_version, success=False, error_message="Missing required fields")
        return

    if not target_column:
        logger.warning("Missing target_column_name; skipping")
        await _send_complete(producer, task_id, user_id, model_id, None, dataset_id, dataset_version, success=False, error_message="Missing target_column_name")
        return

    try:
        logger.info(f"Downloading drift split: dataset {dataset_id} version {dataset_version}")
        df_drift = download_drift_dataset(user_id, dataset_id, dataset_version)
        if df_drift.empty or len(df_drift) < 2:
            await _send_complete(producer, task_id, user_id, model_id, None, dataset_id, dataset_version, success=False, error_message="Drift split empty or too small")
            return

        feature_cols = [c for c in df_drift.columns if c != target_column]
        if not feature_cols or target_column not in df_drift.columns:
            await _send_complete(producer, task_id, user_id, model_id, None, dataset_id, dataset_version, success=False, error_message="Target or feature columns invalid")
            return

        with tempfile.TemporaryDirectory() as tmp:
            model_dir = os.path.join(tmp, "model")
            os.makedirs(model_dir, exist_ok=True)
            download_model_folder(user_id, model_id, model_version, model_dir)
            load_path = find_autogluon_model_dir(model_dir)
            from autogluon.tabular import TabularPredictor
            predictor = None
            try:
                predictor = TabularPredictor.load(load_path)
            except AssertionError as e:
                msg = str(e)
                # AutoGluon can require exact version and Python match. For pipeline testing, bypass both.
                if "require_version_match" in msg or "require_py_version_match" in msg or "version" in msg.lower():
                    logger.warning(
                        "AutoGluon predictor version/Python mismatch. "
                        "Retrying with require_version_match=False, require_py_version_match=False (NOT for production). "
                        f"Error was: {e}"
                    )
                    try:
                        predictor = TabularPredictor.load(
                            load_path,
                            require_version_match=False,
                            require_py_version_match=False,
                        )
                    except AssertionError as e2:
                        logger.error(f"Still failed after bypassing version checks: {e2}")
                        raise
                else:
                    raise
            if predictor is None:
                raise RuntimeError("Failed to load TabularPredictor")
            retrain_path = os.path.join(tmp, "retrained")
            os.makedirs(retrain_path, exist_ok=True)
            task_type = infer_task_type(df_drift, target_column)
            # -------------------------
            # Drift configuration
            # -------------------------
            logger.info("[Drift] Starting drift configuration!")

            if task_type == "classification":
                if len(df_drift) < 500:
                    window_size = 150
                    drift_strength = 1.5
                else:
                    window_size = 200
                    drift_strength = 0.80
            else:
                if len(df_drift) < 100:
                    window_size = max(20, len(df_drift) // 4)
                    drift_strength = 0.08
                else:
                    window_size = min(200, max(50, len(df_drift) // 10))
                    drift_strength = 0.05

            logger.info("[Drift] Drift Configuration finished!. Using window_size=%s, drift_strength=%s", window_size, drift_strength)

            drifted_df = drift_induction(df_drift, drift_strength=drift_strength, random_state=45, target_col=target_column, task=task_type, n_drifts=10)
            predictor, drift_log, metrics = monitor_drift_and_retrain(
                df=drifted_df,
                predictor=predictor,
                feature_cols=feature_cols,
                target_col=target_column,
                retrain_path=retrain_path,
                window_size=window_size,
                delta=0.2,
                clock=1,
                batch_predict_size=512,
                min_samples_before_detection=30,
                cooldown_samples=30,
                retrain_presets="medium_quality_faster_train",
                verbose=True
            )

            n_drifts = metrics.get("total_drifts", 0)

            if n_drifts == 0:
                # No drift detected: do not upload (retrain_path is empty). Send success with no new model.
                logger.info("[Drift] No concept drift detected; skipping model upload and sending success")
                await _send_complete(
                    producer, task_id, user_id, model_id, model_version, dataset_id, dataset_version,
                    success=True, drift_metrics=metrics, drift_detected=False
                )
                return
            # Drift detected: zip retrained model and upload to DW
            debug_dir = os.path.join(os.getcwd(), "concept_drift_upload_debug")
            os.makedirs(debug_dir, exist_ok=True)
            safe_id = (task_id or "unknown").replace("/", "_").replace("\\", "_")[:50]
            ts = int(time.time())
            dest_retrained = os.path.join(debug_dir, f"{safe_id}_{ts}_retrained")
            dest_full_tmp = os.path.join(debug_dir, f"{safe_id}_{ts}_full_tmp")
            try:
                shutil.copytree(retrain_path, dest_retrained, dirs_exist_ok=True)
                shutil.copytree(tmp, dest_full_tmp, dirs_exist_ok=True)
                logger.info(
                    "Saved upload folder for debugging: retrained=%s, full_tmp=%s",
                    dest_retrained,
                    dest_full_tmp,
                )
            except Exception as copy_err:
                logger.warning("Could not save debug copies: %s", copy_err)
            model_zip = zip_dir(retrain_path)
        new_metadata = upload_model_to_dw(
            user_id=user_id,
            model_id=model_id,
            model_zip_bytes=model_zip,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
        )
        new_version = new_metadata.get("version", "v2")
        logger.info(f"Uploaded retrained model version {new_version}")
        await _send_complete(
            producer, task_id, user_id, model_id, new_version, dataset_id, dataset_version,
            success=True, drift_metrics=metrics, drift_detected=True
        )
    except Exception as e:
        logger.exception(f"Concept drift processing failed: {e}")
        await _send_complete(
            producer, task_id, user_id, model_id, None, dataset_id, dataset_version,
            success=False, error_message=str(e)
        )


async def _send_complete(
    producer: AIOKafkaProducer,
    task_id: str,
    user_id: str,
    model_id: str,
    model_version: str,
    dataset_id: str,
    dataset_version: str,
    success: bool,
    error_message: str = None,
    drift_metrics: dict = None,
    drift_detected: bool = None,
) -> None:
    payload = {
        "task_id": task_id,
        "event_type": "concept-drift-complete",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    if success:
        payload["output"] = {
            "model_id": model_id,
            "model_version": model_version,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "user_id": user_id,
        }
        if drift_detected is not None:
            payload["output"]["drift_detected"] = drift_detected
            if not drift_detected:
                payload["output"]["message"] = "No concept drift detected"
        if drift_metrics:
            payload["output"]["drift_metrics"] = drift_metrics
        payload["failure"] = None
    else:
        payload["output"] = None
        payload["failure"] = {"error_type": "ConceptDriftError", "error_message": error_message or "Concept drift failed"}
    await producer.send_and_wait(KAFKA_DRIFT_COMPLETE_TOPIC, value=payload, key=task_id)
    logger.info(f"Sent concept-drift-complete task_id={task_id} success={success}")


async def run_consumer() -> None:
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        key_serializer=lambda k: (k or "").encode("utf-8"),
    )
    await producer.start()
    consumer = AIOKafkaConsumer(
        KAFKA_DRIFT_TRIGGER_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_CONSUMER_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"Listening to {KAFKA_DRIFT_TRIGGER_TOPIC}; sending completions to {KAFKA_DRIFT_COMPLETE_TOPIC}")
    try:
        async for msg in consumer:
            logger.info("Concept drift trigger received: %s", json.dumps(msg.value, indent=2))
            await process_drift_trigger(msg.value, producer)
    finally:
        await consumer.stop()
        await producer.stop()


if __name__ == "__main__":
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        logger.info("Interrupted")
