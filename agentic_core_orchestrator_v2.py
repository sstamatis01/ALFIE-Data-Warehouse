#!/usr/bin/env python3
"""
Agentic Core Orchestrator v2 – configured for compliance_alerts_synthetic_30000.csv

This script orchestrates the full ML pipeline using the compliance alerts dataset as the
input example. Use this version when running the flow with:
  - Dataset: compliance_alerts_synthetic_30000.csv (columns: labels, text)
  - Target column: labels
  - Task type: classification (tabular)

Pipeline:
1. Listening to dataset-events → start bias-detection task via Task Manager
2. Listening to bias-complete-events → start automl task via Task Manager
3. Listening to automl-complete-events → start concept-drift task via Task Manager
4. Listening to concept-drift-complete-events → start xai task via Task Manager
5. Listening to xai-complete-events → report back to user (final step)

Usage:
  TASK_MANAGER_URL=http://localhost:8102 \
  KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  API_BASE=http://localhost:8000 \
  python agentic_core_orchestrator_v2.py

Example: Upload compliance_alerts_synthetic_30000.csv as dataset (e.g. dataset_id=compliance_alerts),
then this orchestrator will use target_column_name=labels and task_type=classification for
bias detection, AutoML, and concept drift.
"""

import os
import asyncio
import json
import logging
import signal
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from collections import defaultdict

from aiokafka import AIOKafkaConsumer
import requests
import pandas as pd
from io import BytesIO

from task_manager.client.client import TaskManagerClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("agentic_core_v2")

# --- v2: Defaults for compliance_alerts_synthetic_30000.csv (labels, text) ---
DEFAULT_TARGET_COLUMN = "labels"
DEFAULT_TASK_TYPE = "classification"
DEFAULT_TASK_CATEGORY = "tabular"

# Configuration
TASK_MANAGER_URL = os.getenv("TASK_MANAGER_URL", "http://localhost:8102")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "alfie.iti.gr:9092")
KAFKA_DATASET_TOPIC = os.getenv("KAFKA_DATASET_TOPIC", "dataset-events")
KAFKA_BIAS_TOPIC = os.getenv("KAFKA_BIAS_TOPIC", "bias-detection-complete-events")
KAFKA_AUTOML_TOPIC = os.getenv("KAFKA_AUTOML_TOPIC", "automl-complete-events")
KAFKA_CONCEPT_DRIFT_TOPIC = os.getenv("KAFKA_CONCEPT_DRIFT_TOPIC", "concept-drift-complete-events")
KAFKA_XAI_TOPIC = os.getenv("KAFKA_XAI_TOPIC", "xai-complete-events")

# Default API_BASE based on where Kafka is (deployment vs local).
if os.getenv("API_BASE"):
    API_BASE = os.getenv("API_BASE")
elif "alfie.iti.gr" in KAFKA_BOOTSTRAP_SERVERS:
    API_BASE = "https://alfie.iti.gr/autodw"
else:
    API_BASE = "http://localhost:8000"

# In-memory task correlation: (user_id, dataset_id) -> task_ids and task config
# Use _corr_key(user_id, dataset_id) so different users don't overwrite each other.
def _corr_key(user_id: str, dataset_id: str) -> str:
    return f"{user_id}_{dataset_id}"


task_correlation: Dict[str, Dict[str, str]] = defaultdict(dict)


def fetch_dataset_metadata(user_id: str, dataset_id: str, version: str = None) -> dict:
    """Fetch dataset metadata from API. If version is given, fetch that specific version."""
    if version:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/version/{version}"
    else:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def read_csv_with_encoding(file_data: bytes) -> pd.DataFrame:
    """Try to read CSV with multiple encodings."""
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-16']
    for encoding in encodings:
        try:
            df = pd.read_csv(BytesIO(file_data), encoding=encoding)
            logger.info(f"Successfully read CSV with encoding: {encoding}")
            return df
        except (UnicodeDecodeError, Exception):
            continue
    try:
        df = pd.read_csv(BytesIO(file_data), encoding='utf-8', encoding_errors='ignore')
        logger.warning("Read CSV with 'ignore' errors - some characters may be missing")
        return df
    except Exception as e:
        logger.error(f"Failed to read CSV with all encodings: {e}")
        raise


def download_dataset_file(user_id: str, dataset_id: str, version: str = None, split: str = None) -> bytes:
    """Download dataset file. For split datasets, pass split='train'|'test'|'drift' to get only that subset."""
    if version:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/version/{version}/download"
    else:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/download"
    if split and split in ("train", "test", "drift"):
        url += "?" if "?" not in url else "&"
        url += f"split={split}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def extract_dataset_folder(zip_bytes: bytes, extract_to: str = "temp_dataset") -> list:
    """Extract ZIP and return list of extracted file paths. Caller should pass a unique extract_to (e.g. include user_id and a short uuid) to avoid cross-request collisions."""
    import zipfile
    os.makedirs(extract_to, exist_ok=True)
    with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    extracted_files = []
    for root, dirs, files in os.walk(extract_to):
        for file in files:
            extracted_files.append(os.path.join(root, file))
    return extracted_files


async def start_task_via_task_manager(
    task_manager_client: TaskManagerClient,
    task_name: str,
    user_id: str,
    input_data: dict,
    timeout_sec: int = 3600,
) -> Optional[str]:
    """Start a task via Task Manager REST API. Returns task ID if successful."""
    try:
        task = await task_manager_client.start_task(
            user_id=user_id,
            name=task_name,
            input=input_data,
            timeout_sec=timeout_sec,
        )
        logger.info(f"[Task Manager] Started {task_name} task: {task.id}")
        return task.id
    except Exception as e:
        logger.error(f"[Task Manager] Failed to start {task_name} task: {e}", exc_info=True)
        return None


# --- Consumer for dataset events ---
async def consume_dataset_events(
    task_manager_client: TaskManagerClient,
    shutdown_event: asyncio.Event,
):
    """Listen to dataset-events and start bias-detection task via Task Manager (v2: target=labels)."""
    consumer = AIOKafkaConsumer(
        KAFKA_DATASET_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-v2-dataset-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core v2] Started consumer for topic: {KAFKA_DATASET_TOPIC} (target_column={DEFAULT_TARGET_COLUMN})")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
            value = msg.value
            logger.info(f"[Dataset Event] Message received: {json.dumps(value, indent=2)}")

            try:
                if value.get("event_type") != "dataset.uploaded":
                    logger.info(f"Skipping non-upload event: {value.get('event_type')}")
                    continue

                dataset = value.get("dataset", {})
                user_id = dataset.get("user_id")
                dataset_id = dataset.get("dataset_id")
                is_folder = dataset.get("is_folder", False)
                file_count = dataset.get("file_count", 1)
                custom_meta = dataset.get("custom_metadata") or {}
                has_split = bool(custom_meta.get("split"))

                if not user_id or not dataset_id:
                    logger.warning("Missing user_id/dataset_id in event; skipping")
                    continue

                dataset_version = dataset.get("version") or "v1"
                logger.info(f"[Agentic Core v2] Processing dataset_id={dataset_id} version={dataset_version}")

                task_category = DEFAULT_TASK_CATEGORY
                ckey = _corr_key(user_id, dataset_id)
                task_correlation[ckey]["task_category"] = task_category
                task_correlation[ckey]["target_column_name"] = DEFAULT_TARGET_COLUMN
                logger.info(f"[Agentic Core v2] task_category={task_category} target_column={DEFAULT_TARGET_COLUMN} (compliance alerts flow)")

                meta = fetch_dataset_metadata(user_id, dataset_id, dataset_version)
                is_mitigated = meta.get("custom_metadata", {}).get("is_mitigated", False)
                tags = meta.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                has_mitigated_tag = "mitigated" in [tag.lower() for tag in tags]

                if is_mitigated or has_mitigated_tag:
                    logger.info(f"[Agentic Core v2] Dataset {dataset_id} is already mitigated - skipping bias detection")
                    continue

                download_split = "train" if has_split else None
                if download_split:
                    logger.info(f"Downloading version {dataset_version} with split={download_split}")
                file_bytes = download_dataset_file(user_id, dataset_id, dataset_version, split=download_split)
                logger.info(f"Downloaded dataset: {len(file_bytes)} bytes")

                df = None
                extracted_files = []

                if is_folder:
                    try:
                        unique_suffix = uuid.uuid4().hex[:8]
                        extract_dir = f"temp_dataset_{user_id}_{dataset_id}_{dataset_version}_{unique_suffix}"
                        extracted_files = extract_dataset_folder(file_bytes, extract_dir)
                        csv_files = [f for f in extracted_files if f.endswith('.csv')]
                        if csv_files:
                            with open(csv_files[0], 'rb') as f:
                                df = read_csv_with_encoding(f.read())
                    except Exception as e:
                        logger.warning(f"Could not extract/parse folder dataset: {e}")
                else:
                    try:
                        df = read_csv_with_encoding(file_bytes)
                        logger.info(f"Loaded single file dataset with shape {df.shape}")
                    except Exception as e:
                        logger.warning(f"Could not parse dataset as CSV: {e}")

                # v2: bias-detection input for compliance_alerts (target=labels, classification)
                input_data = {
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "user_id": user_id,
                    "target_column_name": DEFAULT_TARGET_COLUMN,
                    "task_type": DEFAULT_TASK_TYPE,
                    "task_category": task_category,
                }
                if task_category == "vision":
                    input_data["filename_column"] = "filename"
                    input_data["label_column"] = "label"
                    input_data["model_size"] = "small"

                task_id = await start_task_via_task_manager(
                    task_manager_client=task_manager_client,
                    task_name="bias-detection",
                    user_id=user_id,
                    input_data=input_data,
                    timeout_sec=3600,
                )
                if task_id:
                    task_correlation[ckey]["bias"] = task_id
                    logger.info(f"[Agentic Core v2] Started bias-detection task: {task_id}")
                else:
                    logger.error(f"[Agentic Core v2] Failed to start bias-detection task for dataset {dataset_id}")

            except Exception as e:
                logger.error(f"Error processing dataset event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("Dataset consumer stopped.")


# --- Consumer for bias events ---
async def consume_bias_events(
    task_manager_client: TaskManagerClient,
    shutdown_event: asyncio.Event,
):
    """Listen to bias-complete-events and start automl task (v2: target=labels)."""
    consumer = AIOKafkaConsumer(
        KAFKA_BIAS_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-v2-bias-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core v2] Started consumer for topic: {KAFKA_BIAS_TOPIC}")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
            value = msg.value
            logger.info(f"[Bias Event] Message received: {json.dumps(value, indent=2)}")

            try:
                task_id = value.get("task_id")
                output = value.get("output")
                failure = value.get("failure")
                if not task_id or failure or not output:
                    if failure:
                        logger.error(f"[Bias Detection Failed] Task {task_id}: {failure.get('error_message', 'Unknown error')}")
                    continue

                user_id = output.get("user_id")
                dataset_id = output.get("dataset_id")
                bias_report_id = output.get("bias_report_id")
                mitigated_dataset_version = output.get("mitigated_dataset_version")

                if not user_id or not dataset_id:
                    continue

                if mitigated_dataset_version:
                    dataset_version = mitigated_dataset_version
                    logger.info(f"[AutoML Trigger] Using MITIGATED dataset version: {dataset_version}")
                else:
                    dataset_version = output.get("dataset_version")
                    if not dataset_version:
                        try:
                            dataset_metadata = fetch_dataset_metadata(user_id, dataset_id)
                            dataset_version = dataset_metadata.get("version", "v1")
                        except Exception:
                            dataset_version = "v1"
                    logger.info(f"[AutoML Trigger] Using dataset version: {dataset_version}")

                task_category = DEFAULT_TASK_CATEGORY
                ckey = _corr_key(user_id, dataset_id)
                task_correlation[ckey]["task_category"] = task_category

                # v2: AutoML input for compliance_alerts (target_column_name=labels, task_type=classification)
                input_data = {
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "user_id": user_id,
                    "task_category": task_category,
                    "time_budget": "10",
                    "target_column_name": DEFAULT_TARGET_COLUMN,
                    "task_type": DEFAULT_TASK_TYPE,
                }

                automl_task_id = await start_task_via_task_manager(
                    task_manager_client=task_manager_client,
                    task_name="automl",
                    user_id=user_id,
                    input_data=input_data,
                    timeout_sec=3600,
                )
                if automl_task_id:
                    task_correlation[ckey]["automl"] = automl_task_id
                    task_correlation[ckey]["target_column_name"] = DEFAULT_TARGET_COLUMN
                    logger.info(f"[Agentic Core v2] Started AutoML task: {automl_task_id}")
                else:
                    logger.error(f"[Agentic Core v2] Failed to start AutoML task for dataset {dataset_id}")

            except Exception as e:
                logger.error(f"Error processing bias event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("Bias consumer stopped.")


# --- Consumer for automl events ---
async def consume_automl_events(
    task_manager_client: TaskManagerClient,
    shutdown_event: asyncio.Event,
):
    """Listen to automl-complete-events and start concept-drift task (v2: target_column_name=labels)."""
    consumer = AIOKafkaConsumer(
        KAFKA_AUTOML_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-v2-automl-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core v2] Started consumer for topic: {KAFKA_AUTOML_TOPIC}")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
            value = msg.value
            logger.info(f"[AutoML Event] Message received: {json.dumps(value, indent=2)}")

            try:
                task_id = value.get("task_id")
                output = value.get("output")
                failure = value.get("failure")
                if not task_id or failure or not output:
                    if failure:
                        logger.error(f"[AutoML Failed] Task {task_id}: {failure.get('error_message', 'Unknown error')}")
                    continue

                user_id = output.get("user_id")
                dataset_id = output.get("dataset_id")
                model_id = output.get("model_id")
                model_version = output.get("model_version", "v1")
                dataset_version = output.get("dataset_version")

                if not user_id or not model_id:
                    continue

                if not dataset_version:
                    try:
                        dataset_metadata = fetch_dataset_metadata(user_id, dataset_id)
                        dataset_version = dataset_metadata.get("version", "v1")
                    except Exception:
                        dataset_version = "v1"

                ckey = _corr_key(user_id, dataset_id)
                target_column_name = task_correlation.get(ckey, {}).get("target_column_name", DEFAULT_TARGET_COLUMN)

                drift_input = {
                    "user_id": user_id,
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "model_id": model_id,
                    "model_version": model_version,
                    "target_column_name": target_column_name,
                    "window_size": 100,
                }
                concept_drift_task_id = await start_task_via_task_manager(
                    task_manager_client=task_manager_client,
                    task_name="concept-drift",
                    user_id=user_id,
                    input_data=drift_input,
                    timeout_sec=3600,
                )
                if concept_drift_task_id:
                    task_correlation[ckey]["concept_drift"] = concept_drift_task_id
                    logger.info(f"[Agentic Core v2] Started concept-drift task: {concept_drift_task_id}")
                else:
                    logger.error(f"[Agentic Core v2] Failed to start concept-drift task for model {model_id}")

            except Exception as e:
                logger.error(f"Error processing automl event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("AutoML consumer stopped.")


# --- Consumer for concept drift events ---
async def consume_concept_drift_events(
    task_manager_client: TaskManagerClient,
    shutdown_event: asyncio.Event,
):
    """Listen to concept-drift-complete-events and start xai task."""
    consumer = AIOKafkaConsumer(
        KAFKA_CONCEPT_DRIFT_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-v2-concept-drift-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core v2] Started consumer for topic: {KAFKA_CONCEPT_DRIFT_TOPIC}")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
            value = msg.value
            logger.info(f"[Concept Drift Event] Message received: {json.dumps(value, indent=2)}")

            try:
                task_id = value.get("task_id")
                output = value.get("output")
                failure = value.get("failure")
                if not task_id:
                    continue
                # On failure we still have output with context (user_id, dataset_id, model_id, etc.) so we can proceed to XAI
                if not output:
                    logger.warning("[Concept Drift Event] No output in message; skipping XAI trigger")
                    continue

                if failure:
                    logger.error(f"[Concept Drift Failed] Task {task_id}: {failure.get('error_message', 'Unknown error')}")
                    logger.info("[Agentic Core v2] Proceeding to XAI anyway (flow continues on concept-drift failure)")

                user_id = output.get("user_id")
                dataset_id = output.get("dataset_id")
                model_id = output.get("model_id")
                model_version = output.get("model_version", "v1")
                dataset_version = output.get("dataset_version")
                drift_metrics = output.get("drift_metrics", {})

                if not user_id or not model_id:
                    continue

                if not failure:
                    logger.info(f"[User Report] Concept drift completed for model {model_id} (version {model_version})")
                    if drift_metrics:
                        logger.info(f"  Drift metrics: total_drifts={drift_metrics.get('total_drifts', 'n/a')}, final_accuracy={drift_metrics.get('final_accuracy', 'n/a')}")

                if not dataset_version:
                    try:
                        dataset_metadata = fetch_dataset_metadata(user_id, dataset_id)
                        dataset_version = dataset_metadata.get("version", "v1")
                    except Exception:
                        dataset_version = "v1"

                input_data = {
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "user_id": user_id,
                    "model_id": model_id,
                    "model_version": model_version,
                    "report_type": "lime",
                    "level": "expert"
                }
                xai_task_id = await start_task_via_task_manager(
                    task_manager_client=task_manager_client,
                    task_name="xai",
                    user_id=user_id,
                    input_data=input_data,
                    timeout_sec=3600,
                )
                if xai_task_id:
                    ckey = _corr_key(user_id, dataset_id)
                    task_correlation[ckey]["xai"] = xai_task_id
                    logger.info(f"[Agentic Core v2] Started XAI task: {xai_task_id}")
                else:
                    logger.error(f"[Agentic Core v2] Failed to start XAI task for model {model_id}")

            except Exception as e:
                logger.error(f"Error processing concept drift event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("Concept drift consumer stopped.")


# --- Consumer for XAI events ---
async def consume_xai_events(shutdown_event: asyncio.Event):
    """Listen to xai-complete-events (final step) and report back to user."""
    consumer = AIOKafkaConsumer(
        KAFKA_XAI_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-v2-xai-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core v2] Started consumer for topic: {KAFKA_XAI_TOPIC}")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
            value = msg.value
            logger.info(f"[XAI Event] Message received: {json.dumps(value, indent=2)}")

            try:
                task_id = value.get("task_id")
                output = value.get("output")
                failure = value.get("failure")
                if not task_id or failure or not output:
                    if failure:
                        logger.error(f"[XAI Failed] Task {task_id}: {failure.get('error_message', 'Unknown error')}")
                    continue

                user_id = output.get("user_id")
                model_id = output.get("model_id")
                dataset_id = output.get("dataset_id")
                xai_report_id = output.get("xai_report_id")

                logger.info(f"[User Report] XAI report generated for model {model_id}")
                logger.info(f"  XAI Report ID: {xai_report_id}")
                logger.info(f"  Dataset ID: {dataset_id}")
                logger.info("=" * 80)
                logger.info("ML PIPELINE COMPLETED! (v2 – compliance alerts flow)")
                logger.info(f"  Dataset: {dataset_id}  Model: {model_id}  User: {user_id}")
                logger.info("=" * 80)

            except Exception as e:
                logger.error(f"Error processing XAI event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("XAI consumer stopped.")


async def run_consumers():
    """Run all consumers concurrently."""
    shutdown_event = asyncio.Event()
    def handle_shutdown():
        logger.info("Shutting down...")
        shutdown_event.set()
    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, handle_shutdown)
        loop.add_signal_handler(signal.SIGINT, handle_shutdown)
    except (NotImplementedError, ValueError):
        logger.info("Signal handlers not available (Windows), use Ctrl+C to stop")

    task_manager_client = TaskManagerClient(TASK_MANAGER_URL)
    await task_manager_client.__aenter__()

    try:
        await asyncio.gather(
            consume_dataset_events(task_manager_client, shutdown_event),
            consume_bias_events(task_manager_client, shutdown_event),
            consume_automl_events(task_manager_client, shutdown_event),
            consume_concept_drift_events(task_manager_client, shutdown_event),
            consume_xai_events(shutdown_event),
        )
    finally:
        await task_manager_client.__aexit__(None, None, None)
        logger.info("[Agentic Core v2] Task Manager client closed")


if __name__ == "__main__":
    try:
        logger.info("=" * 80)
        logger.info("AGENTIC CORE v2 – ML PIPELINE ORCHESTRATOR (compliance_alerts_synthetic_30000)")
        logger.info("  Target column: labels | Task type: classification | Task category: tabular")
        logger.info("=" * 80)
        logger.info(f"Task Manager URL: {TASK_MANAGER_URL}")
        logger.info(f"Kafka Bootstrap: {KAFKA_BOOTSTRAP_SERVERS}")
        logger.info("=" * 80)
        asyncio.run(run_consumers())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
