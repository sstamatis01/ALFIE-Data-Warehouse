#!/usr/bin/env python3
"""
Kafka Consumer Example for AutoML Trigger Events

This consumer listens to the automl-trigger-events topic (from Agentic Core).
When an AutoML trigger event is received, this consumer should:
- Load the dataset
- Identify the ML problem (classification, regression, etc.)
- Train an AI model using AutoML
- Save the model to the Data Warehouse (which triggers automl-events)

Usage:
  KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  KAFKA_AUTOML_TRIGGER_TOPIC=automl-trigger-events \
  KAFKA_CONSUMER_GROUP=automl-consumer \
  python kafka_automl_consumer_example.py
"""

import os
import asyncio
import json
import logging
from datetime import datetime, timezone
from aiokafka import AIOKafkaConsumer
import requests
import pandas as pd
from io import BytesIO
import io
import zipfile

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("kafka_automl_consumer")

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "alfie.iti.gr:9092")
KAFKA_AUTOML_TRIGGER_TOPIC = os.getenv("KAFKA_AUTOML_TRIGGER_TOPIC", "automl-trigger-events")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "automl-consumer")

API_BASE = os.getenv("API_BASE", "http://localhost:8000")


def fetch_dataset_metadata(user_id: str, dataset_id: str, version: str = None) -> dict:
    """Fetch dataset metadata from the Data Warehouse API (specific version or latest)"""
    if version:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/version/{version}"
    else:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def read_csv_with_encoding(file_data: bytes) -> pd.DataFrame:
    """
    Read CSV bytes with robust fallbacks.

    Uses multiple encodings and the Python parser to reduce tokenizer failures on malformed rows.
    """
    encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1", "utf-16"]

    for encoding in encodings:
        try:
            df = pd.read_csv(
                BytesIO(file_data),
                encoding=encoding,
                engine="python",
                on_bad_lines="skip",
            )
            logger.info(f"Successfully read CSV with encoding: {encoding}")
            return df
        except Exception:
            continue

    # Last resort: ignore undecodable chars and skip malformed lines
    try:
        df = pd.read_csv(
            BytesIO(file_data),
            encoding="utf-8",
            encoding_errors="ignore",
            engine="python",
            on_bad_lines="skip",
        )
        logger.warning("Read CSV with lenient parser (encoding_errors='ignore', on_bad_lines='skip')")
        return df
    except Exception as e:
        logger.error(f"Failed to read CSV with all encodings: {e}")
        raise


def load_tabular_dataframe(file_bytes: bytes) -> pd.DataFrame:
    """
    Load tabular data from bytes.

    Supports:
    - raw CSV bytes
    - ZIP bytes containing one or more CSV files (uses first CSV)
    """
    import zipfile

    try:
        return read_csv_with_encoding(file_bytes)
    except Exception:
        pass

    try:
        with zipfile.ZipFile(BytesIO(file_bytes), "r") as zf:
            csv_names = [
                n
                for n in zf.namelist()
                if n.lower().endswith(".csv") and not n.startswith("__")
            ]
            if not csv_names:
                raise ValueError("ZIP does not contain any CSV files")
            with zf.open(csv_names[0]) as f:
                return read_csv_with_encoding(f.read())
    except Exception as e:
        raise ValueError(f"Could not load tabular dataframe from downloaded bytes: {e}")


def download_dataset_file(user_id: str, dataset_id: str, version: str = None, split: str = None) -> bytes:
    """Download dataset file (single file or folder as ZIP). If split is train/test/drift, download that subset."""
    if version:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/version/{version}/download"
    else:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/download"
    if split and split in ("train", "test", "drift"):
        url += f"?split={split}"
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


def _zip_dir(path: str) -> bytes:
    """Zip a local directory and return bytes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(path):
            for fname in files:
                abspath = os.path.join(root, fname)
                arcname = os.path.relpath(abspath, path).replace("\\", "/")
                zf.write(abspath, arcname)
    buf.seek(0)
    return buf.getvalue()


def upload_model_to_dw(user_id: str, model_id: str, dataset_id: str, model_folder_path: str,
                       model_type: str, framework: str = "sklearn", accuracy: float = None,
                       dataset_version: str = None, task_id: str | None = None) -> dict:
    """
    Upload trained model to Data Warehouse
    This will automatically trigger an automl-events message
    Version is auto-incremented by the DW
    """
    url = f"{API_BASE}/ai-models/upload/folder/{user_id}"

    # Include dataset version in description for data lineage tracking
    description = f"AutoML trained model for {model_type}"
    if dataset_version:
        description += f" (trained on dataset {dataset_id} version {dataset_version})"
    else:
        description += f" (trained on dataset {dataset_id})"

    model_zip = _zip_dir(model_folder_path)
    files = {"zip_file": ("model.zip", io.BytesIO(model_zip), "application/zip")}
    data = {
        "model_id": model_id,
        "name": f"AutoML Model - {model_id}",
        "description": description,
        "framework": framework,
        "model_type": model_type,
        "training_dataset": dataset_id,  # Link to dataset
        "training_accuracy": accuracy,
        "preserve_structure": "true",
    }

    headers = {"X-Task-ID": task_id} if task_id else None
    r = requests.post(url, files=files, data=data, headers=headers, timeout=120)
    r.raise_for_status()
    return r.json()


async def process_automl_trigger(event: dict) -> None:
    """
    Process an AutoML trigger event from Agentic Core

    Simplified event structure:
    {
        "task_id": "automl_task_<...>",
        "event_type": "automl-trigger",
        "timestamp": "...",
        "input": {
            "dataset_id": "...",
            "dataset_version": "v1",
            "user_id": "...",
            "target_column_name": "target",
            "task_type": "classification"
        }
    }
    """
    try:
        task_id = event.get("task_id")
        input_obj = event.get("input", {})
        user_id = input_obj.get("user_id")
        dataset_id = input_obj.get("dataset_id")
        dataset_version = input_obj.get("dataset_version", "v1")  # Default to v1 for backward compatibility
        target_column = input_obj.get("target_column_name")
        task_type = input_obj.get("task_type")
        time_budget = event.get("time_budget", "10")

        if not user_id or not dataset_id:
            logger.warning("Missing user_id or dataset_id in event; skipping")
            return

        logger.info(f"Processing AutoML trigger for dataset {dataset_id} version {dataset_version}")
        logger.info(f"  User: {user_id}")
        logger.info(f"  Target column: {target_column}")
        logger.info(f"  Task type: {task_type}")
        logger.info(f"  Time budget: {time_budget} minutes")

        # Step 1: Fetch dataset metadata and download file
        try:
            metadata = fetch_dataset_metadata(user_id, dataset_id, dataset_version)

            # Detect dataset shape and split support from metadata
            is_folder = metadata.get("is_folder", False)
            file_count = metadata.get("file_count", 1)
            has_split = bool(metadata.get("custom_metadata", {}).get("split"))
            download_split = "train" if has_split else None

            logger.info(f"Dataset type: {'FOLDER' if is_folder else 'SINGLE FILE'}")
            if is_folder:
                logger.info(f"File count: {file_count}")
            if download_split:
                logger.info(f"Dataset has train/test/drift split; downloading '{download_split}' split for dummy AutoML")

            file_bytes = download_dataset_file(
                user_id, dataset_id, dataset_version, split=download_split
            )
            logger.info(f"Dataset downloaded: {len(file_bytes)} bytes")
        except Exception as e:
            logger.error(f"Failed to fetch dataset: {e}")
            return

        # Step 2: Load dataset into pandas
        df = None

        try:
            df = load_tabular_dataframe(file_bytes)
            logger.info(f"Dataset loaded: {df.shape[0]} rows, {df.shape[1]} columns")
            if target_column and target_column not in df.columns:
                logger.warning(
                    f"Target column '{target_column}' not found in dataset columns; dummy upload will proceed."
                )
        except Exception as e:
            logger.error(f"Failed to parse dataset: {e}")
            return

        # Step 3: Identify the problem and train model
        # TODO: Replace this with actual AutoML training logic
        # For now, we'll use a dummy local model folder for testing

        logger.info("=" * 80)
        logger.info("Training model (using dummy local /model folder for testing)")
        logger.info(f"  - Target column: {target_column}")
        logger.info(f"  - Task type: {task_type}")
        logger.info(f"  - Dataset shape: {df.shape}")
        logger.info("=" * 80)

        # Generate model ID
        model_id = f"automl_{dataset_id}_{int(datetime.now(timezone.utc).timestamp())}"

        # Use dummy local model folder for testing
        dummy_model_folder = "model"

        if not os.path.isdir(dummy_model_folder):
            logger.warning(f"Dummy model folder not found: {dummy_model_folder}")
            logger.info("Skipping model upload - provide a model folder in the repository root to test")
            return

        # Upload the trained model to DW
        try:
            logger.info(f"Uploading model to DW: {model_id}")
            result = upload_model_to_dw(
                user_id=user_id,
                model_id=model_id,
                dataset_id=dataset_id,
                model_folder_path=dummy_model_folder,
                model_type=task_type,
                framework="sklearn",
                accuracy=0.92,  # Dummy accuracy for testing
                dataset_version=dataset_version,
                task_id=task_id
            )
            logger.info(f"✅ Model uploaded to DW successfully!")
            logger.info(f"   Model ID: {model_id}")
            logger.info(f"   Response: {json.dumps(result, indent=2, default=str)}")
            logger.info("   AutoML event will be automatically sent by the DW")
        except Exception as e:
            logger.error(f"Failed to upload model to DW: {e}", exc_info=True)
            return

        logger.info(f"AutoML processing completed for dataset {dataset_id}")

    except Exception as e:
        logger.error(f"Error processing AutoML trigger event: {e}", exc_info=True)


async def run_consumer() -> None:
    """Main consumer loop"""
    consumer = AIOKafkaConsumer(
        KAFKA_AUTOML_TRIGGER_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_CONSUMER_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )

    logger.info("Starting AutoML Trigger consumer...")
    logger.info(f"Bootstrap servers: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Topic: {KAFKA_AUTOML_TRIGGER_TOPIC}")
    logger.info(f"Consumer group: {KAFKA_CONSUMER_GROUP}")
    logger.info("Waiting for AutoML trigger events from Agentic Core...")

    await consumer.start()

    try:
        async for msg in consumer:
            key = msg.key
            value = msg.value

            logger.info("=" * 80)
            logger.info("AutoML Trigger Message received")
            logger.info(f"  Partition={msg.partition} Offset={msg.offset}")
            logger.info(f"  Key={key}")
            logger.info(f"  Event={json.dumps(value, indent=2)}")
            logger.info("=" * 80)

            # Process the AutoML trigger event
            # The process_automl_trigger function extracts input data from the event
            await process_automl_trigger(value)

    finally:
        await consumer.stop()
        logger.info("AutoML Trigger consumer stopped")


if __name__ == "__main__":
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
