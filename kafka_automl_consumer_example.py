#!/usr/bin/env python3
"""
Kafka Consumer Example for AutoML Trigger Events

This consumer listens to the automl-trigger-events topic (from Agentic Core).
When an AutoML trigger event is received, this consumer:
- Loads the dataset (for validation)
- Simulates AutoML training (dummy - no actual AutoML service)
- Produces an automl-complete event to Kafka

This is a dummy implementation that doesn't call actual AutoML services.
It's designed to test the Kafka orchestration flow without requiring
an AutoML service to be running.

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
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import requests
import pandas as pd
from io import BytesIO
from dotenv import load_dotenv, find_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("kafka_automl_consumer")

load_dotenv(find_dotenv())

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_AUTOML_TRIGGER_TOPIC = os.getenv("KAFKA_AUTOML_TRIGGER_TOPIC", "automl-trigger-events")
KAFKA_AUTOML_COMPLETE_TOPIC = os.getenv("KAFKA_AUTOML_COMPLETE_TOPIC", "automl-complete-events")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "automl-consumer")

# Data Warehouse API configuration
# Default to localhost (for running outside Docker)
# Can be overridden with API_BASE (full URL) or DW_HOST+DW_PORT
DW_HOST = os.getenv("DW_HOST", "localhost")
DW_PORT = os.getenv("DW_PORT", "8000")
# Support both API_BASE (full URL) and DW_HOST+DW_PORT (components)
if os.getenv("API_BASE"):
    API_BASE = os.getenv("API_BASE")
else:
    API_BASE = f"http://{DW_HOST}:{DW_PORT}"


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
    Try to read CSV with multiple encodings
    
    Handles files with different encodings:
    - utf-8: Standard
    - latin-1 (ISO-8859-1): Western European
    - cp1252 (Windows-1252): Windows default
    - utf-16: Some Excel exports
    """
    from io import BytesIO
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


def download_dataset_file(user_id: str, dataset_id: str, version: str = None) -> bytes:
    """Download dataset file (single file or folder as ZIP) - specific version or latest"""
    if version:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/version/{version}/download"
    else:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/download"
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


async def send_automl_complete_event(
    producer: AIOKafkaProducer,
    task_id: str,
    user_id: str,
    model_id: str,
    model_version: str,
    dataset_id: str,
    dataset_version: str,
    success: bool = True,
    error_message: str | None = None
) -> None:
    """
    Send AutoML completion event to Kafka
    
    Event structure matches the format expected by Agentic Core:
    {
        "task_id": "...",
        "event_type": "automl-complete",
        "timestamp": "...",
        "output": {
            "model_id": "...",
            "model_version": "...",
            "dataset_id": "...",
            "dataset_version": "...",
            "user_id": "..."
        },
        "failure": null
    }
    """
    if not producer:
        logger.error("Kafka producer not initialized; skipping AutoML completion event")
        return
    
    payload = {
        "task_id": task_id,
        "event_type": "automl-complete",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    
    if success:
        payload["output"] = {
            "model_id": model_id,
            "model_version": model_version,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "user_id": user_id
        }
        payload["failure"] = None
    else:
        payload["output"] = None
        payload["failure"] = {
            "error_type": "AutoMLError",
            "error_message": error_message or "AutoML training failed"
        }
    
    try:
        logger.info(f"Sending AutoML completion event to topic: {KAFKA_AUTOML_COMPLETE_TOPIC}")
        logger.info(f"Payload: {json.dumps(payload, indent=2, default=str)}")
        await producer.send_and_wait(KAFKA_AUTOML_COMPLETE_TOPIC, value=payload, key=task_id)
        logger.info(f"✅ AutoML completion event sent successfully to Kafka for task_id={task_id}")
    except Exception as e:
        logger.error(f"❌ Failed to send AutoML completion event to Kafka: {e}", exc_info=True)
        logger.error(f"   Topic: {KAFKA_AUTOML_COMPLETE_TOPIC}")
        logger.error(f"   Task ID: {task_id}")
        raise


async def process_automl_trigger(event: dict, producer: AIOKafkaProducer) -> None:
    """
    Process an AutoML trigger event from Agentic Core
    
    Event structure (supports both formats):
    {
        "task_id": "automl_task_<...>",
        "event_type": "automl-trigger",
        "timestamp": "...",
        "input": {
            "dataset_id": "...",
            "dataset_version": "v1",
            "user_id": "...",
            "target_column_name": "target",
            "task_type": "classification",
            "task_category": "tabular"
        }
    }
    
    OR (for backward compatibility):
    {
        "event_type": "automl-trigger.reported",
        "dataset_id": "dataset123",
        "user_id": "user123",
        "target_column_name": "target",
        "task_type": "classification",
        "time_budget": "10",
        "timestamp": "2025-10-10T12:00:00.000000"
    }
    """
    try:
        # Extract task_id from event (if present)
        task_id = event.get("task_id")
        
        # Extract input object (new structure) or use event directly (backward compatibility)
        input_obj = event.get("input", event)
        
        user_id = input_obj.get("user_id")
        dataset_id = input_obj.get("dataset_id")
        dataset_version = input_obj.get("dataset_version", "v1")  # Default to v1 for backward compatibility
        target_column = input_obj.get("target_column_name")
        task_type = input_obj.get("task_type")
        time_budget = input_obj.get("time_budget", event.get("time_budget", "10"))  # Check both places
        task_category = input_obj.get("task_category", "tabular")
        
        if not user_id or not dataset_id:
            logger.warning("Missing user_id or dataset_id in event; skipping")
            return
        
        if not task_id:
            logger.warning("Missing task_id in event; generating one for completion event")
            task_id = f"automl_task_{dataset_id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        logger.info(f"Processing AutoML trigger for dataset {dataset_id} version {dataset_version}")
        logger.info(f"  Task ID: {task_id}")
        logger.info(f"  User: {user_id}")
        logger.info(f"  Target column: {target_column}")
        logger.info(f"  Task type: {task_type}")
        logger.info(f"  Task category: {task_category}")
        logger.info(f"  Time budget: {time_budget} minutes")
        
        # Step 1: Fetch dataset metadata and download file (for validation)
        try:
            logger.info(f"Fetching dataset metadata from: {API_BASE}")
            metadata = fetch_dataset_metadata(user_id, dataset_id, dataset_version)
            logger.info(f"Dataset metadata fetched successfully")
            
            # Check if dataset is a folder or single file
            is_folder = metadata.get("is_folder", False)
            file_count = metadata.get("file_count", 1)
            
            logger.info(f"Dataset type: {'FOLDER' if is_folder else 'SINGLE FILE'}")
            if is_folder:
                logger.info(f"File count: {file_count}")
            
            # Download dataset file (for validation - we don't actually train)
            logger.info(f"Downloading dataset file from: {API_BASE}")
            file_bytes = download_dataset_file(user_id, dataset_id, dataset_version)
            logger.info(f"Dataset downloaded: {len(file_bytes)} bytes")
        except requests.exceptions.Timeout as e:
            logger.error(f"Timeout while fetching dataset from {API_BASE}")
            logger.error(f"   Error: {e}")
            logger.error(f"   If running in Docker, ensure DW_HOST=api is set")
            logger.error(f"   If running locally, ensure the Data Warehouse API is running on {DW_HOST}:{DW_PORT}")
            # Send failure event
            await send_automl_complete_event(
                producer, task_id, user_id, "", "", dataset_id, dataset_version,
                success=False, error_message=f"Timeout fetching dataset: {e}"
            )
            return
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Failed to connect to Data Warehouse API at {API_BASE}")
            logger.error(f"   Error: {e}")
            logger.error(f"   If running in Docker, ensure DW_HOST=api is set")
            logger.error(f"   If running locally, ensure the Data Warehouse API is running on {DW_HOST}:{DW_PORT}")
            # Send failure event
            await send_automl_complete_event(
                producer, task_id, user_id, "", "", dataset_id, dataset_version,
                success=False, error_message=f"Connection error: {e}"
            )
            return
        except Exception as e:
            logger.error(f"Failed to fetch dataset: {e}")
            logger.error(f"   API Base URL: {API_BASE}")
            # Send failure event
            await send_automl_complete_event(
                producer, task_id, user_id, "", "", dataset_id, dataset_version,
                success=False, error_message=f"Failed to fetch dataset: {e}"
            )
            return
        
        # Step 2: Load dataset into pandas (for validation - we don't actually train)
        df = None
        extracted_files = []
        
        try:
            if is_folder:
                # Handle folder dataset - extract ZIP
                logger.info("Extracting folder dataset...")
                extracted_files = extract_dataset_folder(file_bytes, f"temp_automl_{dataset_id}")
                logger.info(f"Extracted {len(extracted_files)} files:")
                for file_path in extracted_files:
                    logger.info(f"  - {file_path}")
                
                # Find and load a CSV file for validation
                csv_files = [f for f in extracted_files if f.endswith('.csv')]
                if csv_files:
                    logger.info(f"Found {len(csv_files)} CSV file(s), loading first one for validation")
                    with open(csv_files[0], 'rb') as f:
                        csv_bytes = f.read()
                    df = read_csv_with_encoding(csv_bytes)
                    logger.info(f"Dataset loaded: {df.shape[0]} rows, {df.shape[1]} columns")
                else:
                    logger.warning("No CSV files found in folder - proceeding with dummy model")
            else:
                # Handle single file dataset
                df = read_csv_with_encoding(file_bytes)
                logger.info(f"Dataset loaded: {df.shape[0]} rows, {df.shape[1]} columns")
                
        except Exception as e:
            logger.warning(f"Failed to parse dataset (proceeding with dummy model): {e}")
            # Continue anyway - we're just doing dummy processing
        
        # Step 3: Simulate AutoML training (DUMMY - no actual AutoML service)
        logger.info("=" * 80)
        logger.info("Simulating AutoML training (DUMMY - no actual AutoML service)")
        logger.info(f"  - Target column: {target_column}")
        logger.info(f"  - Task type: {task_type}")
        logger.info(f"  - Task category: {task_category}")
        if df is not None:
            logger.info(f"  - Dataset shape: {df.shape}")
        logger.info(f"  - Time budget: {time_budget} minutes")
        logger.info("=" * 80)
        
        # Simulate training delay
        logger.info("Simulating training process...")
        await asyncio.sleep(2)  # Simulate processing time
        
        # Generate dummy model ID and version
        model_id = f"automl_{dataset_id}_{int(datetime.now(timezone.utc).timestamp())}"
        model_version = "v1"  # Dummy version
        
        logger.info(f"✅ Dummy AutoML training completed!")
        logger.info(f"   Model ID: {model_id}")
        logger.info(f"   Model Version: {model_version}")
        logger.info(f"   Dataset: {dataset_id} (version {dataset_version})")
        
        # Step 4: Send automl-complete event to Kafka
        try:
            await send_automl_complete_event(
                producer=producer,
                task_id=task_id,
                user_id=user_id,
                model_id=model_id,
                model_version=model_version,
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                success=True
            )
            logger.info(f"✅ AutoML processing completed for dataset {dataset_id}")
        except Exception as e:
            logger.error(f"Failed to send automl-complete event: {e}", exc_info=True)
            return
        
    except Exception as e:
        logger.error(f"Error processing AutoML trigger event: {e}", exc_info=True)


async def run_consumer() -> None:
    """Main consumer loop - similar to bias detector consumer"""
    consumer = AIOKafkaConsumer(
        KAFKA_AUTOML_TRIGGER_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_CONSUMER_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )
    
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )

    logger.info("Starting AutoML Trigger consumer...")
    logger.info(f"Bootstrap servers: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Topic: {KAFKA_AUTOML_TRIGGER_TOPIC}")
    logger.info(f"Consumer group: {KAFKA_CONSUMER_GROUP}")
    logger.info(f"Data Warehouse API: {API_BASE} (host: {DW_HOST}, port: {DW_PORT})")
    logger.info(f"Output topic: {KAFKA_AUTOML_COMPLETE_TOPIC}")
    logger.info("Waiting for AutoML trigger events from Agentic Core...")
    logger.info("Note: This is a DUMMY consumer - no actual AutoML service is called")

    await consumer.start()
    await producer.start()
    
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
            # The process_automl_trigger function handles both event structures:
            # - New structure with "input" object and "task_id"
            # - Old structure for backward compatibility
            await process_automl_trigger(value, producer)
    
    finally:
        await consumer.stop()
        await producer.stop()
        logger.info("AutoML Trigger consumer stopped")


if __name__ == "__main__":
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
