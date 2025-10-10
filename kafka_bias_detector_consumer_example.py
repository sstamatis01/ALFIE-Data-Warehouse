#!/usr/bin/env python3
"""
Simple Kafka Consumer Example for Dataset Events

Usage:
  KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  KAFKA_DATASET_TOPIC=dataset-events \
  KAFKA_CONSUMER_GROUP=dataset-consumer \
  python kafka_consumer_example.py
"""

import os
import asyncio
import json
import logging
from aiokafka import AIOKafkaConsumer
import requests
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("kafka_consumer_example")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_BIAS_TRIGGER_TOPIC = os.getenv("KAFKA_BIAS_TRIGGER_TOPIC", "bias-trigger-events")
KAFKA_BIAS_TRIGGER_CONSUMER_GROUP = os.getenv("KAFKA_BIAS_TRIGGER_CONSUMER_GROUP", "bias-trigger-consumer")

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


def post_bias_report(user_id: str, dataset_id: str, report: dict, 
                     target_column_name: str = None, task_type: str = None) -> dict:
    url = f"{API_BASE}/bias-reports/"
    payload = {
        "user_id": user_id,
        "dataset_id": dataset_id,
        "report": report,
        "target_column_name": target_column_name,
        "task_type": task_type,
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def build_bias_report(df: pd.DataFrame | None, meta: dict) -> dict:
    # Build a report like the provided example structure
    report: dict = {}
    try:
        if df is not None:
            report["shape"] = [int(df.shape[0]), int(df.shape[1])]  # JSON-friendly
            report["columns"] = list(df.columns.astype(str))
            report["dtypes"] = {col: str(dtype) for col, dtype in df.dtypes.items()}
            # Memory in MB
            mem_bytes = df.memory_usage(deep=True).sum()
            report["memory_usage_MB"] = float(mem_bytes / (1024 * 1024))
            # Summary statistics for numeric columns
            try:
                desc = df.describe(percentiles=[0.25, 0.5, 0.75], include=["number"]).to_dict()
                # Ensure JSON-friendly floats
                clean_desc: dict = {}
                for col, stats in desc.items():
                    clean_desc[col] = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in stats.items()}
                report["summary_statistics"] = clean_desc
            except Exception:
                report["summary_statistics"] = {}
        else:
            # Fallback if we couldn't parse with pandas
            report["shape"] = [int(meta.get("row_count", 0)), len(meta.get("columns", []) or [])]
            report["columns"] = meta.get("columns", []) or []
            report["dtypes"] = meta.get("data_types", {}) or {}
            report["memory_usage_MB"] = None
            report["summary_statistics"] = {}
    except Exception as e:
        logger.warning(f"Failed to build bias report: {e}")
    return report


async def run_consumer() -> None:
    consumer = AIOKafkaConsumer(
        KAFKA_BIAS_TRIGGER_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=KAFKA_BIAS_TRIGGER_CONSUMER_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        key_deserializer=lambda m: m.decode("utf-8") if m else None,
    )

    logger.info("Starting consumer...")
    logger.info(f"Bootstrap servers: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Topic: {KAFKA_BIAS_TRIGGER_TOPIC}")
    logger.info(f"Consumer group: {KAFKA_BIAS_TRIGGER_CONSUMER_GROUP}")

    await consumer.start()
    try:
        async for msg in consumer:
            key = msg.key
            value = msg.value
            logger.info("Message received")
            logger.info(f"  Partition={msg.partition} Offset={msg.offset}")
            logger.info(f"  Key={key}")
            logger.info(f"  Event={json.dumps(value, indent=2)}")

            try:
                dataset = value.get("metadata", {})
                user_id = dataset.get("user_id")
                dataset_id = dataset.get("dataset_id")
                target_column_name = value.get("target_column_name")
                task_type = value.get("task_type")
                logger.info(f"Target column={target_column_name}")
                logger.info(f"Task type={task_type}")
                if not user_id or not dataset_id:
                    logger.warning("Missing user_id/dataset_id in event; skipping")
                    continue

                # Fetch metadata (optional) and download file
                meta = fetch_dataset_metadata(user_id, dataset_id)
                file_bytes = download_dataset_file(user_id, dataset_id)

                # Try to read as CSV with pandas (fallback to bytes length)
                df = None
                try:
                    from io import BytesIO
                    df = pd.read_csv(BytesIO(file_bytes))
                    logger.info(f"Loaded dataset into pandas DataFrame with shape {df.shape}")
                except Exception as e:
                    logger.warning(f"Could not parse file as CSV: {e}; proceeding with raw bytes")

                # Build bias report (profile) per the corrected example
                bias_report = build_bias_report(df, meta)

                # POST bias report to API (include target_column_name and task_type)
                saved = post_bias_report(
                    user_id=user_id, 
                    dataset_id=dataset_id, 
                    report=bias_report,
                    target_column_name=target_column_name,
                    task_type=task_type
                )
                logger.info(f"Saved bias report: {json.dumps(saved, indent=2, default=str)}")
                
                # --- Transformation mitigator placeholder (COMMENTED OUT) ---
                # If a mitigator runs here, you could generate:
                # 1) A transformed dataset (e.g., df_transformed or bytes)
                # 2) A transformation report similar to the provided example
                #
                # Example transformation report structure (numbers as floats):
                # transformation_report = [
                #     {"column": "all", "transformation": "duplicate_removal", "method": "drop_duplicates", "original_value": "15 duplicates", "modified_value": "duplicates removed"},
                #     {"column": "feature_0", "transformation": "skew_correction", "method": "yeo-johnson", "original_value": float(-0.818), "modified_value": float(-0.036)},
                #     ...
                # ]
                #
                # Post transformation report to API:
                # requests.post(
                #     f"{API_BASE}/transformation-reports/",
                #     json={
                #         "user_id": user_id,
                #         "dataset_id": dataset_id,
                #         "version": "v2",
                #         "report": transformation_report,
                #     },
                #     timeout=30,
                # ).raise_for_status()
                #
                # Optionally, upload v2 dataset (disabled to avoid re-triggering consumer):
                # If you export df_transformed to CSV bytes:
                # from io import BytesIO
                # buf = BytesIO()
                # df_transformed.to_csv(buf, index=False)
                # buf.seek(0)
                # files = {"file": ("dataset_v2.csv", buf.getvalue(), "text/csv")}
                # data = {
                #     "user_id": user_id,
                #     "dataset_id": dataset_id,
                #     "name": meta.get("name", dataset_id),
                #     "description": "Mitigated dataset v2",
                #     "version": "v2",
                # }
                # requests.post(f"{API_BASE}/datasets/upload", files=files, data=data, timeout=120).raise_for_status()
                # --- End transformation placeholder ---

            except Exception as proc_err:
                logger.error(f"Processing error: {proc_err}")
            # Send Kafka event (non-blocking failure)

    
    finally:
        await consumer.stop()
        logger.info("Consumer stopped")


if __name__ == "__main__":
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
