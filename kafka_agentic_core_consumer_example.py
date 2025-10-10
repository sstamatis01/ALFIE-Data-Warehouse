#!/usr/bin/env python3
"""
Agentic Core Kafka Consumer

This script orchestrates the entire ML pipeline by listening to multiple topics
and producing trigger events for downstream consumers:

1. Listen to dataset-events → produce bias-trigger-events
2. Listen to bias-events → produce automl-trigger-events  
3. Listen to automl-events → produce xai-trigger-events
4. Listen to xai-events → report back to user (final step)

Usage:
  KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  python kafka_agentic_core_consumer_example.py
"""

import os
import asyncio
import json
import logging
from datetime import datetime
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import requests
import pandas as pd
from io import BytesIO

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("agentic_core")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_DATASET_TOPIC = os.getenv("KAFKA_DATASET_TOPIC", "dataset-events")
KAFKA_BIAS_TOPIC = os.getenv("KAFKA_BIAS_TOPIC", "bias-events")
KAFKA_AUTOML_TOPIC = os.getenv("KAFKA_AUTOML_TOPIC", "automl-events")
KAFKA_XAI_TOPIC = os.getenv("KAFKA_XAI_TOPIC", "xai-events")
KAFKA_BIAS_TRIGGER_TOPIC = os.getenv("KAFKA_BIAS_TRIGGER_TOPIC", "bias-trigger-events")
KAFKA_AUTOML_TRIGGER_TOPIC = os.getenv("KAFKA_AUTOML_TRIGGER_TOPIC", "automl-trigger-events")
KAFKA_XAI_TRIGGER_TOPIC = os.getenv("KAFKA_XAI_TRIGGER_TOPIC", "xai-trigger-events")

API_BASE = os.getenv("API_BASE", "http://localhost:8000")


def fetch_dataset_metadata(user_id: str, dataset_id: str) -> dict:
    url = f"{API_BASE}/datasets/{user_id}/{dataset_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def download_dataset_file(user_id: str, dataset_id: str) -> bytes:
    url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/download"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


# --- Consumer for dataset events ---
async def consume_dataset_events(producer):
    """
    Listen to dataset-events and produce bias-trigger-events
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
            key = msg.key
            value = msg.value
            logger.info(f"[Dataset Event] Message received: {json.dumps(value, indent=2)}")

            try:
                dataset = value.get("dataset", {})
                user_id = dataset.get("user_id")
                dataset_id = dataset.get("dataset_id")

                if not user_id or not dataset_id:
                    logger.warning("Missing user_id/dataset_id in event; skipping")
                    continue

                # Fetch metadata and dataset
                meta = fetch_dataset_metadata(user_id, dataset_id)
                file_bytes = download_dataset_file(user_id, dataset_id)

                df = None
                try:
                    df = pd.read_csv(BytesIO(file_bytes))
                    logger.info(f"Loaded dataset with shape {df.shape}")
                except Exception as e:
                    logger.warning(f"Could not parse dataset as CSV: {e}")

                # TODO: Interact with user to get target column and task type
                # For now, using placeholder values
                logger.info("[User Interaction] TODO: Ask user for target column and task type")
                
                payload = {
                    "event_type": "bias-trigger.reported",
                    "dataset_id": dataset_id,
                    "user_id": user_id,
                    "target_column_name": "target",  # TODO: Get from user
                    "task_type": "classification",   # TODO: Get from user
                    "timestamp": datetime.utcnow().isoformat(),
                    "metadata": meta,
                    "record_count": len(df) if df is not None else None,
                }

                await producer.send_and_wait(
                    topic=KAFKA_BIAS_TRIGGER_TOPIC,
                    key=key,
                    value=payload,
                )
                logger.info(f"[Agentic Core] Produced bias trigger event to {KAFKA_BIAS_TRIGGER_TOPIC}")

            except Exception as e:
                logger.error(f"Error processing dataset event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("Dataset consumer stopped.")


# --- Consumer for bias events ---
async def consume_bias_events(producer):
    """
    Listen to bias-events and produce automl-trigger-events
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
            key = msg.key
            value = msg.value
            logger.info(f"[Bias Event] Message received: {json.dumps(value, indent=2)}")
            
            try:
                user_id = value.get("user_id")
                dataset_id = value.get("dataset_id")
                target_column_name = value.get("target_column_name")
                task_type = value.get("task_type")

                if not user_id or not dataset_id:
                    logger.warning("Missing user_id/dataset_id in bias event; skipping")
                    continue

                # TODO: Report bias results to user
                logger.info(f"[User Report] Bias report completed for dataset {dataset_id}")
                logger.info("[User Interaction] TODO: Report bias findings and ask if user wants to proceed with AutoML")
                
                # Produce AutoML trigger event
                payload = {
                    "event_type": "automl-trigger.reported",
                    "dataset_id": dataset_id,
                    "user_id": user_id,
                    "target_column_name": target_column_name,
                    "task_type": task_type,
                    "time_budget": "10",  # TODO: Get from user or config
                    "timestamp": datetime.utcnow().isoformat(),
                }
                
                await producer.send_and_wait(
                    topic=KAFKA_AUTOML_TRIGGER_TOPIC,
                    key=key,
                    value=payload,
                )
                logger.info(f"[Agentic Core] Produced AutoML trigger event to {KAFKA_AUTOML_TRIGGER_TOPIC}")
                
            except Exception as e:
                logger.error(f"Error processing bias event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("Bias consumer stopped.")


# --- Consumer for automl events ---
async def consume_automl_events(producer):
    """
    Listen to automl-events (model uploaded) and produce xai-trigger-events
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
            key = msg.key
            value = msg.value
            logger.info(f"[AutoML Event] Message received: {json.dumps(value, indent=2)}")

            try:
                user_id = value.get("user_id")
                dataset_id = value.get("dataset_id")
                model_id = value.get("model_id")
                version = value.get("version", "v1")

                if not user_id or not model_id:
                    logger.warning("Missing user_id/model_id in automl event; skipping")
                    continue

                # TODO: Report model training results to user
                logger.info(f"[User Report] Model {model_id} trained successfully")
                logger.info(f"  Training accuracy: {value.get('training_accuracy')}")
                logger.info(f"  Validation accuracy: {value.get('validation_accuracy')}")
                logger.info("[User Interaction] TODO: Ask user if they want XAI explanations")
                
                # Produce XAI trigger event (if dataset_id is available)
                if dataset_id:
                    payload = {
                        "event_type": "xai-trigger.reported",
                        "user_id": user_id,
                        "dataset_id": dataset_id,
                        "model_id": model_id,
                        "version": version,
                        "level": "beginner",  # TODO: Get from user (beginner or expert)
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    
                    await producer.send_and_wait(
                        topic=KAFKA_XAI_TRIGGER_TOPIC,
                        key=key,
                        value=payload,
                    )
                    logger.info(f"[Agentic Core] Produced XAI trigger event to {KAFKA_XAI_TRIGGER_TOPIC}")
                else:
                    logger.warning("No dataset_id in automl event; cannot trigger XAI")

            except Exception as e:
                logger.error(f"Error processing automl event: {e}", exc_info=True)

    finally:
        await consumer.stop()
        logger.info("AutoML consumer stopped.")


# --- Consumer for XAI events ---
async def consume_xai_events():
    """
    Listen to xai-events (final step) and report back to user
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
            key = msg.key
            value = msg.value
            logger.info(f"[XAI Event] Message received: {json.dumps(value, indent=2)}")

            try:
                user_id = value.get("user_id")
                model_id = value.get("model_id")
                dataset_id = value.get("dataset_id")
                report_type = value.get("report_type")
                level = value.get("level")

                # TODO: Report XAI completion to user
                logger.info(f"[User Report] XAI report generated for model {model_id}")
                logger.info(f"  Report type: {report_type}")
                logger.info(f"  Level: {level}")
                logger.info("[User Interaction] TODO: Notify user that XAI report is ready")
                logger.info(f"  View at: {API_BASE}/xai-reports/{user_id}/{dataset_id}/{model_id}/{report_type}/{level}/view")
                
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
    # Create producers for each consumer
    producer1 = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda x: json.dumps(x, default=str).encode("utf-8"),
        key_serializer=lambda x: x.encode("utf-8") if x else None,
    )
    producer2 = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda x: json.dumps(x, default=str).encode("utf-8"),
        key_serializer=lambda x: x.encode("utf-8") if x else None,
    )
    producer3 = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda x: json.dumps(x, default=str).encode("utf-8"),
        key_serializer=lambda x: x.encode("utf-8") if x else None,
    )

    await producer1.start()
    await producer2.start()
    await producer3.start()
    logger.info("[Agentic Core] All producers started")
    
    try:
        # Run all consumers concurrently
        await asyncio.gather(
            consume_dataset_events(producer1),
            consume_bias_events(producer2),
            consume_automl_events(producer3),
            consume_xai_events(),  # No producer needed (final step)
        )
    finally:
        await producer1.stop()
        await producer2.stop()
        await producer3.stop()
        logger.info("[Agentic Core] All producers stopped")


if __name__ == "__main__":
    try:
        logger.info("=" * 80)
        logger.info("AGENTIC CORE - ML PIPELINE ORCHESTRATOR")
        logger.info("=" * 80)
        logger.info("Orchestrating: Dataset → Bias → AutoML → XAI")
        logger.info("=" * 80)
        asyncio.run(run_consumers())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
