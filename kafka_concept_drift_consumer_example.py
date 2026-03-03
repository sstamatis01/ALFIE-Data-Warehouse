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


def monitor_drift_and_retrain(df, predictor, feature_cols, target_col, retrain_path: str, window_size: int = 100):
    """
    ADWIN-based drift detection and retrain on sliding window.
    Returns (predictor, drift_log_df, metrics_dict).
    """
    from river.drift import ADWIN
    from autogluon.tabular import TabularPredictor

    n_rows = len(df)
    logger.info(
        "[Drift] Starting monitoring: rows=%d, target=%s, window_size=%d, retrain_path=%s",
        n_rows,
        target_col,
        window_size,
        retrain_path,
    )
    adwin = ADWIN(delta=0.01, clock=1)
    window_rows = deque(maxlen=window_size)
    events = []
    y_true_all, y_pred_all = [], []
    total_retrain_time = 0.0
    start_time = __import__("time").time()
    log_interval = max(1, n_rows // 10)  # log progress ~10 times over the run

    for i, row in df.iterrows():
        y_true = row[target_col]
        y_pred = predict_autogluon(predictor, row, feature_cols)
        error = 0.0 if y_pred == y_true else 1.0
        y_true_all.append(y_true)
        y_pred_all.append(y_pred)
        window_rows.append(row)
        adwin.update(error)

        if (i + 1) % log_interval == 0 or i == 0:
            correct_so_far = sum(1 for a, b in zip(y_true_all, y_pred_all) if a == b)
            logger.info(
                "[Drift] Progress row %d/%d, cumulative_accuracy=%.4f, window_fill=%d",
                i + 1,
                n_rows,
                correct_so_far / len(y_true_all) if y_true_all else 0,
                len(window_rows),
            )

        if adwin.drift_detected:
            logger.info(
                "[Drift] Concept drift DETECTED at index %d. Retraining on last %d samples at path=%s",
                i,
                len(window_rows),
                retrain_path,
            )
            window_df = pd.DataFrame(list(window_rows))
            retrain_start = __import__("time").time()
            predictor = TabularPredictor(label=target_col, path=retrain_path).fit(train_data=window_df)
            retrain_time = __import__("time").time() - retrain_start
            total_retrain_time += retrain_time
            events.append({"index": i, "window_size": len(window_rows), "retrain_time_seconds": retrain_time})
            # Confirm that fit() wrote to retrain_path (and list contents)
            try:
                contents = []
                for _root, _dirs, files in os.walk(retrain_path):
                    contents.extend(os.path.join(os.path.relpath(_root, retrain_path), f) for f in files)
                logger.info("[Drift] After retrain: path=%s has %d files: %s", retrain_path, len(contents), contents[:20])
            except Exception as e:
                logger.warning("[Drift] Could not list retrain_path after fit: %s", e)

    drift_log = pd.DataFrame(events)
    # Summary: whether any retrain happened (if not, retrain_path stays empty and upload will fail)
    n_drifts = len(events)
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
    total_count = len(y_true_all)
    correct_count = sum(1 for a, b in zip(y_true_all, y_pred_all) if a == b)
    try:
        from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
        # Ensure discrete targets (no mix of multiclass and continuous) for sklearn
        yt = pd.Series(y_true_all)
        yp = pd.Series(y_pred_all)
        if np.issubdtype(yp.dtype, np.floating):
            yp = np.round(yp).astype(int)
        if yt.dtype.kind in ("O", "U", "S") or yp.dtype.kind in ("O", "U", "S"):
            yt, yp = np.array([str(x) for x in yt]), np.array([str(x) for x in yp])
        else:
            yt, yp = np.asarray(yt), np.asarray(yp)
        final_accuracy = accuracy_score(yt, yp)
        f1 = f1_score(yt, yp, average="weighted", zero_division=0)
        precision = precision_score(yt, yp, average="weighted", zero_division=0)
        recall = recall_score(yt, yp, average="weighted", zero_division=0)
    except Exception:
        final_accuracy = f1 = precision = recall = float("nan")
    metrics = {
        "cumulative_accuracy": correct_count / total_count if total_count else float("nan"),
        "final_accuracy": final_accuracy,
        "f1_score": f1,
        "precision": precision,
        "recall": recall,
        "total_drifts": len(events),
        "total_retrain_time_seconds": total_retrain_time,
        "total_runtime_seconds": __import__("time").time() - start_time,
    }
    return predictor, drift_log, metrics


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
            predictor, drift_log, metrics = monitor_drift_and_retrain(
                df_drift, predictor, feature_cols, target_column, retrain_path, window_size=window_size
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
