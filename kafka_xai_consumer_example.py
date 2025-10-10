#!/usr/bin/env python3
"""
Kafka Consumer Example for XAI Trigger Events

This consumer listens to the xai-trigger-events topic (from Agentic Core).
When an XAI trigger event is received, this consumer should:
- Load the dataset and model from the Data Warehouse
- Generate XAI explanations (SHAP, LIME, etc.)
- Create HTML reports for different expertise levels
- Upload the reports to the Data Warehouse (which triggers xai-events)

Usage:
  KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  KAFKA_XAI_TRIGGER_TOPIC=xai-trigger-events \
  KAFKA_CONSUMER_GROUP=xai-consumer \
  python kafka_xai_consumer_example.py
"""

import os
import asyncio
import json
import logging
from datetime import datetime
from aiokafka import AIOKafkaConsumer
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("kafka_xai_consumer")

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_XAI_TRIGGER_TOPIC = os.getenv("KAFKA_XAI_TRIGGER_TOPIC", "xai-trigger-events")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "xai-consumer")

API_BASE = os.getenv("API_BASE", "http://localhost:8000")


def fetch_dataset_metadata(user_id: str, dataset_id: str) -> dict:
    """Fetch dataset metadata from the Data Warehouse API"""
    url = f"{API_BASE}/datasets/{user_id}/{dataset_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def download_dataset_file(user_id: str, dataset_id: str) -> bytes:
    """Download dataset file from the Data Warehouse API"""
    url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/download"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def fetch_model_metadata(user_id: str, model_id: str, version: str = "v1") -> dict:
    """Fetch AI model metadata from the Data Warehouse API"""
    url = f"{API_BASE}/ai-models/{user_id}/{model_id}"
    params = {"version": version}
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def download_model_file(user_id: str, model_id: str, version: str = "v1", filename: str = None) -> bytes:
    """Download AI model file from the Data Warehouse API"""
    url = f"{API_BASE}/ai-models/{user_id}/{model_id}/download"
    params = {"version": version}
    if filename:
        params["filename"] = filename
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.content


def upload_xai_report(user_id: str, dataset_id: str, model_id: str, 
                     report_type: str, level: str, html_file_path: str) -> dict:
    """
    Upload XAI report to Data Warehouse
    This will automatically trigger an xai-events message
    """
    url = f"{API_BASE}/xai-reports/upload/{user_id}"
    
    with open(html_file_path, 'rb') as f:
        files = {'file': (os.path.basename(html_file_path), f, 'text/html')}
        data = {
            'dataset_id': dataset_id,
            'model_id': model_id,
            'report_type': report_type,
            'level': level
        }
        
        r = requests.post(url, files=files, data=data, timeout=120)
        r.raise_for_status()
        return r.json()


async def process_xai_trigger(event: dict) -> None:
    """
    Process an XAI trigger event from Agentic Core
    
    Event structure:
    {
        "event_type": "xai-trigger.reported",
        "user_id": "user123",
        "dataset_id": "dataset123",
        "model_id": "model123",
        "version": "v1",
        "level": "beginner",
        "timestamp": "2025-10-10T12:00:00.000000"
    }
    """
    try:
        user_id = event.get("user_id")
        dataset_id = event.get("dataset_id")
        model_id = event.get("model_id")
        version = event.get("version", "v1")
        level = event.get("level", "beginner")
        
        if not user_id or not dataset_id or not model_id:
            logger.warning("Missing required fields in event; skipping")
            return
        
        logger.info(f"Processing XAI trigger for model {model_id}")
        logger.info(f"  User: {user_id}")
        logger.info(f"  Dataset: {dataset_id}")
        logger.info(f"  Level: {level}")
        
        # Step 1: Fetch dataset
        try:
            dataset_meta = fetch_dataset_metadata(user_id, dataset_id)
            dataset_bytes = download_dataset_file(user_id, dataset_id)
            logger.info(f"Dataset downloaded: {len(dataset_bytes)} bytes")
        except Exception as e:
            logger.error(f"Failed to fetch dataset: {e}")
            return
        
        # Step 2: Fetch model
        try:
            model_meta = fetch_model_metadata(user_id, model_id, version)
            # Optionally download model file if needed
            # model_bytes = download_model_file(user_id, model_id, version)
            logger.info(f"Model metadata fetched: {model_meta.get('name')}")
        except Exception as e:
            logger.error(f"Failed to fetch model: {e}")
            return
        
        # Step 3: Generate XAI explanations
        # TODO: Replace this with actual XAI generation logic
        # For now, we'll use dummy HTML files for testing
        
        logger.info("=" * 80)
        logger.info("Generating XAI explanations (using dummy HTML files for testing)")
        logger.info(f"  - Model: {model_meta.get('name')}")
        logger.info(f"  - Framework: {model_meta.get('framework')}")
        logger.info(f"  - Level: {level}")
        logger.info("=" * 80)
        
        # Use dummy HTML files for testing
        html_file_path_model = f"model-{level}.html"
        html_file_path_data = f"data-{level}.html"
        
        # Upload model explanation report
        if os.path.exists(html_file_path_model):
            try:
                logger.info(f"Uploading model explanation report: {html_file_path_model}")
                result_model = upload_xai_report(
                    user_id=user_id,
                    dataset_id=dataset_id,
                    model_id=model_id,
                    report_type="model_explanation",
                    level=level,
                    html_file_path=html_file_path_model
                )
                logger.info(f"✅ Model explanation report uploaded successfully!")
                logger.info(f"   Report type: model_explanation")
                logger.info(f"   Level: {level}")
                logger.info(f"   Response: {json.dumps(result_model, indent=2, default=str)}")
            except Exception as e:
                logger.error(f"Failed to upload model explanation report: {e}", exc_info=True)
        else:
            logger.warning(f"Model HTML file not found: {html_file_path_model}")
            logger.info(f"Skipping model explanation - create {html_file_path_model} in the root directory to test")
        
        # Upload data explanation report
        if os.path.exists(html_file_path_data):
            try:
                logger.info(f"Uploading data explanation report: {html_file_path_data}")
                result_data = upload_xai_report(
                    user_id=user_id,
                    dataset_id=dataset_id,
                    model_id=model_id,
                    report_type="data_explanation",
                    level=level,
                    html_file_path=html_file_path_data
                )
                logger.info(f"✅ Data explanation report uploaded successfully!")
                logger.info(f"   Report type: data_explanation")
                logger.info(f"   Level: {level}")
                logger.info(f"   Response: {json.dumps(result_data, indent=2, default=str)}")
                logger.info("   XAI events will be automatically sent by the DW")
            except Exception as e:
                logger.error(f"Failed to upload data explanation report: {e}", exc_info=True)
        else:
            logger.warning(f"Data HTML file not found: {html_file_path_data}")
            logger.info(f"Skipping data explanation - create {html_file_path_data} in the root directory to test")
        
        logger.info(f"XAI processing completed for model {model_id}")
        
    except Exception as e:
        logger.error(f"Error processing XAI trigger event: {e}", exc_info=True)


async def run_consumer() -> None:
    """Main consumer loop"""
    consumer = AIOKafkaConsumer(
        KAFKA_XAI_TRIGGER_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_CONSUMER_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )

    logger.info("Starting XAI Trigger consumer...")
    logger.info(f"Bootstrap servers: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Topic: {KAFKA_XAI_TRIGGER_TOPIC}")
    logger.info(f"Consumer group: {KAFKA_CONSUMER_GROUP}")
    logger.info("Waiting for XAI trigger events from Agentic Core...")

    await consumer.start()
    
    try:
        async for msg in consumer:
            key = msg.key
            value = msg.value
            
            logger.info("=" * 80)
            logger.info("XAI Trigger Message received")
            logger.info(f"  Partition={msg.partition} Offset={msg.offset}")
            logger.info(f"  Key={key}")
            logger.info(f"  Event={json.dumps(value, indent=2)}")
            logger.info("=" * 80)
            
            # Process the XAI trigger event
            await process_xai_trigger(value)
    
    finally:
        await consumer.stop()
        logger.info("XAI Trigger consumer stopped")


if __name__ == "__main__":
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
