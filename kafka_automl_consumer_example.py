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
from datetime import datetime
from aiokafka import AIOKafkaConsumer
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
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "automl-consumer")

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
# AutoML ports
AUTOML_PORT = os.getenv("AUTOML_PORT", 8001)
MAIN_AUTOML_URL = f"http://localhost:{AUTOML_PORT}"
AUTOML_TABULAR_URL = f"{MAIN_AUTOML_URL}/automl_tabular/best_model"


def upload_model_to_dw(user_id: str, model_id: str, dataset_id: str, model_file_path: str, 
                       model_type: str, framework: str = "sklearn", accuracy: float = None) -> dict:
    """
    Upload trained model to Data Warehouse
    This will automatically trigger an automl-events message
    Version is auto-incremented by the DW
    """
    url = f"{API_BASE}/ai-models/upload/single/{user_id}"

    with open(model_file_path, 'rb') as f:
        files = {'file': (os.path.basename(model_file_path), f)}
        data = {
            'model_id': model_id,
            'name': f"AutoML Model - {model_id}",
            'description': f"AutoML trained model for {model_type}",
            'framework': framework,
            'model_type': model_type,
            'training_dataset': dataset_id,  # Link to dataset
            'training_accuracy': accuracy,
        }

        r = requests.post(url, files=files, data=data, timeout=120)
        r.raise_for_status()
        return r.json()


async def process_automl_trigger(event: dict) -> None:
    """
    Process an AutoML trigger event from Agentic Core
    
    Event structure:
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
        user_id = event.get("user_id")
        dataset_id = event.get("dataset_id")
        target_column = event.get("target_column_name")
        task_type = event.get("task_type")
        time_budget = event.get("time_budget", "10")
        task_category = event.get("task_category", "tabular")
        
        if not user_id or not dataset_id:
            logger.warning("Missing user_id or dataset_id in event; skipping")
            return
        
        logger.info(f"Processing AutoML trigger for dataset {dataset_id}")
        logger.info(f"  User: {user_id}")
        logger.info(f"  Target column: {target_column}")
        logger.info(f"  Task type: {task_type}")
        logger.info(f"  Time budget: {time_budget} minutes")
        
        
        if task_category == "tabular":
            data = {
                "user_id" : user_id,
                "dataset_id": dataset_id,
                "target_column_name": target_column,
                "task_type": task_type,
                "time_budget": time_budget
            }
            
            r = requests.post(AUTOML_TABULAR_URL, data=data, timeout=120)
            r.raise_for_status()
            logger.info("Automl processing done and uploaded models to AutoDW")
        else:
            logger.error("Task category does not exist")
            return

    #     # generate model id
    #     model_id = f"automl_{dataset_id}_{int(datetime.utcnow().timestamp())}"
    #
    #     # Use dummy model.pkl file for testing
    #     dummy_model_path = "model.pkl"
    #
    #     if not os.path.exists(dummy_model_path):
    #         logger.warning(f"Dummy model file not found: {dummy_model_path}")
    #         logger.info("Skipping model upload - create a dummy model.pkl file in the root directory to test")
    #         return
    #
    #     # Upload the trained model to DW
    #     try:
    #         logger.info(f"Uploading model to DW: {model_id}")
    #         result = upload_model_to_dw(
    #             user_id=user_id,
    #             model_id=model_id,
    #             dataset_id=dataset_id,
    #             model_file_path=dummy_model_path,
    #             model_type=task_type,
    #             framework="sklearn",
    #             accuracy=0.92  # Dummy accuracy for testing
    #         )
    #         logger.info(f"✅ Model uploaded to DW successfully!")
    #         logger.info(f"   Model ID: {model_id}")
    #         logger.info(f"   Response: {json.dumps(result, indent=2, default=str)}")
    #         logger.info("   AutoML event will be automatically sent by the DW")
    #     except Exception as e:
    #         logger.error(f"Failed to upload model to DW: {e}", exc_info=True)
    #         return
    #
    #     logger.info(f"AutoML processing completed for dataset {dataset_id}")
    #
    # except Exception as e:
    #     logger.error(f"Error processing AutoML trigger event: {e}", exc_info=True)
    #

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
            await process_automl_trigger(value)
    
    finally:
        await consumer.stop()
        logger.info("AutoML Trigger consumer stopped")


if __name__ == "__main__":
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")

