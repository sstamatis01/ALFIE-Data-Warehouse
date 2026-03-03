#!/usr/bin/env python3
"""
Agentic Core Orchestrator

This script orchestrates the entire ML pipeline by:
1. Listening to dataset-events → start bias-detection task via Task Manager
2. Listening to bias-complete-events → start automl task via Task Manager
3. Listening to automl-complete-events → start concept-drift task via Task Manager
4. Listening to concept-drift-complete-events → start xai task via Task Manager
5. Listening to xai-complete-events → report back to user (final step)

Tabular vs Vision (fault logic for now):
- Single CSV file uploaded → task_category "tabular" (bias + automl tabular)
- Zipped folder uploaded → task_category "vision" (bias + automl vision)

The automl-trigger-events consumer (e.g. kafka_automl_consumer_example_v3.py) routes
by task_category to AutoML Tabular or AutoML Vision.

All task creation goes through Task Manager REST API instead of producing
trigger messages directly.

Usage:
  TASK_MANAGER_URL=http://localhost:8102 \
  KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  API_BASE=http://localhost:8000 \
  python agentic_core_orchestrator.py
"""

import os
import asyncio
import json
import logging
import signal
from datetime import datetime, timezone
from typing import Dict, List, Optional
from collections import defaultdict

from aiokafka import AIOKafkaConsumer
import requests
import pandas as pd
from io import BytesIO

from task_manager.client.client import TaskManagerClient

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("agentic_core")

# Configuration
TASK_MANAGER_URL = os.getenv("TASK_MANAGER_URL", "http://localhost:8102")
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_DATASET_TOPIC = os.getenv("KAFKA_DATASET_TOPIC", "dataset-events")
KAFKA_BIAS_TOPIC = os.getenv("KAFKA_BIAS_TOPIC", "bias-detection-complete-events")
KAFKA_AUTOML_TOPIC = os.getenv("KAFKA_AUTOML_TOPIC", "automl-complete-events")
KAFKA_CONCEPT_DRIFT_TOPIC = os.getenv("KAFKA_CONCEPT_DRIFT_TOPIC", "concept-drift-complete-events")
KAFKA_XAI_TOPIC = os.getenv("KAFKA_XAI_TOPIC", "xai-complete-events")

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

# In-memory task correlation: dataset_id -> task_ids and task_category
# Format: {dataset_id: {"bias": task_id, "automl": task_id, "concept_drift": task_id, "xai": task_id, "task_category": "tabular"|"vision", "target_column_name": str}}
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
    """
    Try to read CSV with multiple encodings
    
    Common encodings:
    - utf-8: Standard
    - latin-1 (ISO-8859-1): Western European
    - cp1252 (Windows-1252): Windows default
    - utf-16: Some Excel exports
    """
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1', 'utf-16']
    
    for encoding in encodings:
        try:
            df = pd.read_csv(BytesIO(file_data), encoding=encoding)
            logger.info(f"Successfully read CSV with encoding: {encoding}")
            return df
        except (UnicodeDecodeError, Exception):
            continue
    
    # If all encodings fail, try with error handling
    try:
        df = pd.read_csv(BytesIO(file_data), encoding='utf-8', encoding_errors='ignore')
        logger.warning("Read CSV with 'ignore' errors - some characters may be missing")
        return df
    except Exception as e:
        logger.error(f"Failed to read CSV with all encodings: {e}")
        raise


def download_dataset_file(user_id: str, dataset_id: str, version: str = None, split: str = None) -> bytes:
    """Download dataset file. Pass version to get the exact version that triggered the event (avoids wrong/latest). For split datasets, pass split='train' to get only train subset."""
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
    """
    Extract ZIP file containing dataset folder
    
    Returns:
        List of extracted file paths
    """
    import zipfile
    import os
    from io import BytesIO
    
    # Create extraction directory
    os.makedirs(extract_to, exist_ok=True)
    
    # Extract ZIP
    with zipfile.ZipFile(BytesIO(zip_bytes), 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    
    # List extracted files
    extracted_files = []
    for root, dirs, files in os.walk(extract_to):
        for file in files:
            file_path = os.path.join(root, file)
            extracted_files.append(file_path)
    
    return extracted_files


async def start_task_via_task_manager(
    task_manager_client: TaskManagerClient,
    task_name: str,
    user_id: str,
    input_data: dict,
    timeout_sec: int = 3600,
) -> Optional[str]:
    """
    Start a task via Task Manager REST API.
    
    Returns:
        Task ID if successful, None otherwise
    """
    try:
        task = await task_manager_client.start_task(
            user_id=user_id,
            name=task_name,
            input=input_data,
            timeout_sec=timeout_sec,
        )
        logger.info(f"[Task Manager] Started {task_name} task: {task.id}")
        logger.info(f"  State: {task.state}")
        return task.id
    except Exception as e:
        logger.error(f"[Task Manager] Failed to start {task_name} task: {e}", exc_info=True)
        return None


# --- Consumer for dataset events ---
async def consume_dataset_events(
    task_manager_client: TaskManagerClient,
    shutdown_event: asyncio.Event,
):
    """
    Listen to dataset-events and start bias-detection task via Task Manager
    """
    consumer = AIOKafkaConsumer(
        KAFKA_DATASET_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-dataset-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core] Started consumer for topic: {KAFKA_DATASET_TOPIC}")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
                
            key = msg.key
            value = msg.value
            logger.info(f"[Dataset Event] Message received: {json.dumps(value, indent=2)}")

            try:
                # Handle dataset.uploaded events
                if value.get("event_type") != "dataset.uploaded":
                    logger.info(f"Skipping non-upload event: {value.get('event_type')}")
                    continue

                dataset = value.get("dataset", {})
                user_id = dataset.get("user_id")
                dataset_id = dataset.get("dataset_id")
                is_folder = dataset.get("is_folder", False)
                file_count = dataset.get("file_count", 1)
                custom_meta = dataset.get("custom_metadata") or {}
                has_split = bool(custom_meta.get("split"))  # train/test/drift split from DW

                if not user_id or not dataset_id:
                    logger.warning("Missing user_id/dataset_id in event; skipping")
                    continue

                # Use the version from the event so we always act on the dataset that triggered this event (not "latest")
                dataset_version = dataset.get("version") or "v1"
                logger.info(f"[Agentic Core] Processing dataset_id={dataset_id} version={dataset_version} (from event)")

                logger.info(f"Dataset type: {'FOLDER' if is_folder else 'SINGLE FILE'}")
                if is_folder:
                    logger.info(f"File count: {file_count}")
                if has_split:
                    logger.info(f"Dataset has train/test/drift split (tabular)")

                # TEMPORARY OVERRIDE (for pipeline testing):
                # Force tabular end-to-end so AutoML + Concept Drift flow is exercised
                # even if dataset inference is inconsistent due to splitting changes.
                task_category = "tabular"
                task_correlation[dataset_id]["task_category"] = task_category
                logger.info(f"[Agentic Core] task_category={task_category} (TEMP override: forced tabular)")

                # Fetch metadata for this exact version
                meta = fetch_dataset_metadata(user_id, dataset_id, dataset_version)
                
                # Check if dataset is already mitigated - skip bias detection if so
                # Check both custom_metadata flag and tags as fallback
                is_mitigated = meta.get("custom_metadata", {}).get("is_mitigated", False)
                tags = meta.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                has_mitigated_tag = "mitigated" in [tag.lower() for tag in tags]
                
                if is_mitigated or has_mitigated_tag:
                    logger.info(f"[Agentic Core] Dataset {dataset_id} is already mitigated - skipping bias detection")
                    if is_mitigated:
                        logger.info(f"  Mitigated from version: {meta.get('custom_metadata', {}).get('mitigated_from_version', 'unknown')}")
                    else:
                        logger.info(f"  Detected via 'mitigated' tag")
                    continue
                
                # Download the dataset for this exact version. For split datasets, get only train split so we get one CSV (no mixed content).
                download_split = "train" if has_split else None
                if download_split:
                    logger.info(f"Downloading version {dataset_version} with split={download_split} (split dataset)")
                file_bytes = download_dataset_file(user_id, dataset_id, dataset_version, split=download_split)
                logger.info(f"Downloaded dataset: {len(file_bytes)} bytes")

                df = None
                extracted_files = []
                
                if is_folder:
                    # Handle folder download - extract ZIP (for split we only have train/ content in the zip)
                    try:
                        logger.info("Extracting folder dataset...")
                        extracted_files = extract_dataset_folder(file_bytes, f"temp_dataset_{dataset_id}_{dataset_version}")
                        logger.info(f"Extracted {len(extracted_files)} files:")
                        for file_path in extracted_files:
                            logger.info(f"  - {file_path}")
                        
                        # TODO: Process multiple files as needed
                        # For now, try to find and load a CSV file
                        csv_files = [f for f in extracted_files if f.endswith('.csv')]
                        if csv_files:
                            logger.info(f"Found {len(csv_files)} CSV file(s), loading first one for analysis")
                            with open(csv_files[0], 'rb') as f:
                                csv_bytes = f.read()
                            df = read_csv_with_encoding(csv_bytes)
                            logger.info(f"Loaded CSV with shape {df.shape}")
                        
                    except Exception as e:
                        logger.warning(f"Could not extract/parse folder dataset: {e}")
                else:
                    # Handle single file download
                    try:
                        df = read_csv_with_encoding(file_bytes)
                        logger.info(f"Loaded single file dataset with shape {df.shape}")
                    except Exception as e:
                        logger.warning(f"Could not parse dataset as CSV: {e}")

                # TODO: Interact with user to get target column and task type
                # For now, using placeholder values
                logger.info("[User Interaction] TODO: Ask user for target column and task type")
                
                # Start bias-detection task via Task Manager (include task_category for downstream)
                input_data = {
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "user_id": user_id,
                    "target_column_name": "signature",  # TODO: Get from user (tabular)
                    "task_type": "classification",  # TODO: Get from user
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
                    # Store correlation
                    task_correlation[dataset_id]["bias"] = task_id
                    logger.info(f"[Agentic Core] Started bias-detection task via Task Manager: {task_id}")
                else:
                    logger.error(f"[Agentic Core] Failed to start bias-detection task for dataset {dataset_id}")

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
    """
    Listen to bias-complete-events and start automl task via Task Manager
    """
    consumer = AIOKafkaConsumer(
        KAFKA_BIAS_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-bias-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core] Started consumer for topic: {KAFKA_BIAS_TOPIC}")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
                
            key = msg.key
            value = msg.value
            logger.info(f"[Bias Event] Message received: {json.dumps(value, indent=2)}")
            
            try:
                task_id = value.get("task_id")
                output = value.get("output")
                failure = value.get("failure")
                
                if not task_id:
                    logger.warning("Missing task_id in bias completion event; skipping")
                    continue
                
                if failure:
                    logger.error(f"[Bias Detection Failed] Task {task_id}: {failure.get('error_message', 'Unknown error')}")
                    continue
                
                if not output:
                    logger.warning(f"[Bias Detection] Task {task_id} completed but no output provided")
                    continue
                
                user_id = output.get("user_id")
                dataset_id = output.get("dataset_id")
                bias_report_id = output.get("bias_report_id")
                mitigated_dataset_version = output.get("mitigated_dataset_version")

                if not user_id or not dataset_id:
                    logger.warning("Missing user_id/dataset_id in bias completion event; skipping")
                    continue

                # TODO: Report bias results to user
                logger.info(f"[User Report] Bias report completed for dataset {dataset_id}")
                logger.info(f"  Bias Report ID: {bias_report_id}")
                if mitigated_dataset_version:
                    logger.info(f"  ✅ Mitigation performed - mitigated dataset version: {mitigated_dataset_version}")
                logger.info("[User Interaction] TODO: Report bias findings and ask if user wants to proceed with AutoML")
                
                # Prioritize mitigated_dataset_version over dataset_version
                # If mitigation was performed, use the mitigated version for AutoML training
                if mitigated_dataset_version:
                    dataset_version = mitigated_dataset_version
                    logger.info(f"[AutoML Trigger] Using MITIGATED dataset version: {dataset_version}")
                    logger.info(f"  This ensures AutoML trains on the bias-corrected dataset")
                else:
                    # Get dataset version from bias event output or fetch metadata
                    dataset_version = output.get("dataset_version")
                    if not dataset_version:
                        # Fallback: fetch from API (get latest version)
                        try:
                            dataset_metadata = fetch_dataset_metadata(user_id, dataset_id)
                            dataset_version = dataset_metadata.get("version", "v1")
                        except Exception:
                            dataset_version = "v1"  # Default fallback
                    logger.info(f"[AutoML Trigger] Using original dataset version: {dataset_version}")
                
                # TEMPORARY OVERRIDE (for pipeline testing): force tabular for AutoML triggers.
                task_category = "tabular"
                logger.info(f"[AutoML Trigger] task_category={task_category} (TEMP override: forced tabular)")
                task_correlation[dataset_id]["task_category"] = task_category
                
                # Start AutoML task via Task Manager (match kafka_automl_consumer_example_v3.py input)
                input_data = {
                    "dataset_id": dataset_id,
                    "dataset_version": dataset_version,
                    "user_id": user_id,
                    "task_category": task_category,
                    "time_budget": "10",  # minutes
                }
                # Since we force tabular, always send the tabular fields.
                input_data["target_column_name"] = "signature"  # TODO: Get from user
                input_data["task_type"] = "classification"   # TODO: Get from user
                
                automl_task_id = await start_task_via_task_manager(
                    task_manager_client=task_manager_client,
                    task_name="automl",
                    user_id=user_id,
                    input_data=input_data,
                    timeout_sec=3600,
                )
                
                if automl_task_id:
                    # Store correlation and target_column for downstream concept drift
                    task_correlation[dataset_id]["automl"] = automl_task_id
                    task_correlation[dataset_id]["target_column_name"] = input_data.get("target_column_name", "signature")
                    logger.info(f"[Agentic Core] Started AutoML task via Task Manager: {automl_task_id}")
                else:
                    logger.error(f"[Agentic Core] Failed to start AutoML task for dataset {dataset_id}")
                
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
    """
    Listen to automl-complete-events and start concept-drift task via Task Manager.
    Concept drift runs after AutoML and before XAI.
    """
    consumer = AIOKafkaConsumer(
        KAFKA_AUTOML_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-automl-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core] Started consumer for topic: {KAFKA_AUTOML_TOPIC}")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
                
            key = msg.key
            value = msg.value
            logger.info(f"[AutoML Event] Message received: {json.dumps(value, indent=2)}")

            try:
                task_id = value.get("task_id")
                output = value.get("output")
                failure = value.get("failure")
                
                if not task_id:
                    logger.warning("Missing task_id in automl completion event; skipping")
                    continue
                
                if failure:
                    logger.error(f"[AutoML Failed] Task {task_id}: {failure.get('error_message', 'Unknown error')}")
                    continue
                
                if not output:
                    logger.warning(f"[AutoML] Task {task_id} completed but no output provided")
                    continue
                
                user_id = output.get("user_id")
                dataset_id = output.get("dataset_id")
                model_id = output.get("model_id")
                model_version = output.get("model_version", "v1")
                dataset_version = output.get("dataset_version")

                if not user_id or not model_id:
                    logger.warning("Missing user_id/model_id in automl completion event; skipping")
                    continue

                logger.info(f"[User Report] Model {model_id} trained successfully; triggering concept drift")
                logger.info(f"  Dataset ID: {dataset_id}")

                if not dataset_version:
                    try:
                        dataset_metadata = fetch_dataset_metadata(user_id, dataset_id)
                        dataset_version = dataset_metadata.get("version", "v1")
                    except Exception:
                        dataset_version = "v1"

                target_column_name = task_correlation.get(dataset_id, {}).get("target_column_name", "signature")

                # Start concept-drift task via Task Manager (after AutoML, before XAI)
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
                    task_correlation[dataset_id]["concept_drift"] = concept_drift_task_id
                    logger.info(f"[Agentic Core] Started concept-drift task via Task Manager: {concept_drift_task_id}")
                else:
                    logger.error(f"[Agentic Core] Failed to start concept-drift task for model {model_id}")

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
    """
    Listen to concept-drift-complete-events and start xai task via Task Manager.
    XAI runs on the (possibly drift-retrained) model.
    """
    consumer = AIOKafkaConsumer(
        KAFKA_CONCEPT_DRIFT_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-concept-drift-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core] Started consumer for topic: {KAFKA_CONCEPT_DRIFT_TOPIC}")

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
                    logger.warning("Missing task_id in concept drift completion event; skipping")
                    continue
                
                if failure:
                    logger.error(f"[Concept Drift Failed] Task {task_id}: {failure.get('error_message', 'Unknown error')}")
                    continue
                
                if not output:
                    logger.warning(f"[Concept Drift] Task {task_id} completed but no output provided")
                    continue
                
                user_id = output.get("user_id")
                dataset_id = output.get("dataset_id")
                model_id = output.get("model_id")
                model_version = output.get("model_version", "v1")  # Drift-retrained model version
                dataset_version = output.get("dataset_version")
                drift_metrics = output.get("drift_metrics", {})

                if not user_id or not model_id:
                    logger.warning("Missing user_id/model_id in concept drift completion event; skipping")
                    continue

                logger.info(f"[User Report] Concept drift completed for model {model_id} (version {model_version})")
                if drift_metrics:
                    logger.info(f"  Drift metrics: total_drifts={drift_metrics.get('total_drifts', 'n/a')}, final_accuracy={drift_metrics.get('final_accuracy', 'n/a')}")
                logger.info("[Agentic Core] Triggering XAI for drift-adapted model")
                
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
                    task_correlation[dataset_id]["xai"] = xai_task_id
                    logger.info(f"[Agentic Core] Started XAI task via Task Manager: {xai_task_id}")
                else:
                    logger.error(f"[Agentic Core] Failed to start XAI task for model {model_id}")

            except Exception as e:
                logger.error(f"Error processing concept drift event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("Concept drift consumer stopped.")


# --- Consumer for XAI events ---
async def consume_xai_events(shutdown_event: asyncio.Event):
    """
    Listen to xai-complete-events (final step) and report back to user
    """
    consumer = AIOKafkaConsumer(
        KAFKA_XAI_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="agentic-core-xai-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    await consumer.start()
    logger.info(f"[Agentic Core] Started consumer for topic: {KAFKA_XAI_TOPIC}")

    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                break
                
            key = msg.key
            value = msg.value
            logger.info(f"[XAI Event] Message received: {json.dumps(value, indent=2)}")

            try:
                task_id = value.get("task_id")
                output = value.get("output")
                failure = value.get("failure")
                
                if not task_id:
                    logger.warning("Missing task_id in xai completion event; skipping")
                    continue
                
                if failure:
                    logger.error(f"[XAI Failed] Task {task_id}: {failure.get('error_message', 'Unknown error')}")
                    continue
                
                if not output:
                    logger.warning(f"[XAI] Task {task_id} completed but no output provided")
                    continue
                
                user_id = output.get("user_id")
                model_id = output.get("model_id")
                dataset_id = output.get("dataset_id")
                xai_report_id = output.get("xai_report_id")

                # TODO: Report XAI completion to user
                logger.info(f"[User Report] XAI report generated for model {model_id}")
                logger.info(f"  XAI Report ID: {xai_report_id}")
                logger.info(f"  Dataset ID: {dataset_id}")
                logger.info("[User Interaction] TODO: Notify user that XAI report is ready")
                logger.info(f"  View at: {API_BASE}/xai-reports/{user_id}/{dataset_id}/{model_id}/lime/beginner/view")
                
                logger.info("=" * 80)
                logger.info("ML PIPELINE COMPLETED!")
                logger.info(f"  Dataset: {dataset_id}")
                logger.info(f"  Model: {model_id}")
                logger.info(f"  User: {user_id}")
                logger.info("=" * 80)

            except Exception as e:
                logger.error(f"Error processing XAI event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("XAI consumer stopped.")


# --- Main runner ---
async def run_consumers():
    """Run all consumers concurrently"""
    # Setup graceful shutdown
    shutdown_event = asyncio.Event()
    
    def handle_shutdown():
        logger.info("Shutting down...")
        shutdown_event.set()
    
    # Windows-safe signal handling
    try:
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, handle_shutdown)
        loop.add_signal_handler(signal.SIGINT, handle_shutdown)
    except (NotImplementedError, ValueError):
        # Windows doesn't support signal handlers in asyncio
        logger.info("Signal handlers not available (Windows), use Ctrl+C to stop")
    
    # Create Task Manager client (shared across all consumers)
    # We need to keep it open for the entire duration, so we manage lifecycle manually
    task_manager_client = TaskManagerClient(TASK_MANAGER_URL)
    await task_manager_client.__aenter__()
    
    try:
        # Run all consumers concurrently
        await asyncio.gather(
            consume_dataset_events(task_manager_client, shutdown_event),
            consume_bias_events(task_manager_client, shutdown_event),
            consume_automl_events(task_manager_client, shutdown_event),
            consume_concept_drift_events(task_manager_client, shutdown_event),
            consume_xai_events(shutdown_event),  # No Task Manager client needed (final step)
        )
    finally:
        await task_manager_client.__aexit__(None, None, None)
        logger.info("[Agentic Core] Task Manager client closed")


if __name__ == "__main__":
    try:
        logger.info("=" * 80)
        logger.info("AGENTIC CORE - ML PIPELINE ORCHESTRATOR")
        logger.info("=" * 80)
        logger.info("Orchestrating: Dataset → Bias → AutoML → Concept Drift → XAI")
        logger.info(f"Task Manager URL: {TASK_MANAGER_URL}")
        logger.info(f"Kafka Bootstrap: {KAFKA_BOOTSTRAP_SERVERS}")
        logger.info("=" * 80)
        asyncio.run(run_consumers())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
