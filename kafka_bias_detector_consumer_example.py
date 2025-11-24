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
from importlib.metadata import distribution

import numpy as np
from aiokafka import AIOKafkaConsumer
import requests
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("kafka_consumer_example")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_BIAS_TRIGGER_TOPIC = os.getenv("KAFKA_BIAS_TRIGGER_TOPIC", "bias-detection-trigger-events")
KAFKA_BIAS_TRIGGER_CONSUMER_GROUP = os.getenv("KAFKA_BIAS_TRIGGER_CONSUMER_GROUP", "bias-trigger-consumer")

# Use Docker service name if KAFKA_BOOTSTRAP_SERVERS points to kafka:29092, otherwise use localhost
if "kafka:" in KAFKA_BOOTSTRAP_SERVERS:
    API_BASE = os.getenv("API_BASE", "http://api:8000")
else:
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


def clean_for_json(obj):
    """Recursively clean data structure to be JSON serializable by replacing NaN/inf with None"""
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_for_json(v) for v in obj]
    elif isinstance(obj, (np.floating, float)):
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj


def post_bias_report(user_id: str, dataset_id: str, report: dict, 
                     target_column_name: str = None, task_type: str = None,
                     dataset_version: str = "v1", task_id: str | None = None) -> dict:
    url = f"{API_BASE}/bias-reports/"
    payload = {
        "user_id": user_id,
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "report": report,
        "target_column_name": target_column_name,
        "task_type": task_type,
    }
    headers = {}
    if task_id:
        headers["X-Task-ID"] = task_id
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def build_bias_report(df: pd.DataFrame | None, meta: dict) -> dict:
    # Build a report like the provided example structure
    report: dict = {}
    try:
        if df is not None:
            # 1. Basic info
            report["shape"] = [int(df.shape[0]), int(df.shape[1])]  # JSON-friendly
            report["columns"] = list(df.columns.astype(str))
            report["dtypes"] = {col: str(dtype) for col, dtype in df.dtypes.items()}
            # Memory in MB
            mem_bytes = df.memory_usage(deep=True).sum()
            report["memory_usage_MB"] = float(mem_bytes / (1024 * 1024))
            # 2. Summary statistics for numeric columns
            try:
                desc = df.describe(percentiles=[0.25, 0.5, 0.75], include=["number"]).to_dict()
                # Ensure JSON-friendly floats
                clean_desc: dict = {}
                for col, stats in desc.items():
                    clean_desc[col] = {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in stats.items()}
                report["summary_statistics"] = clean_desc
            except Exception:
                report["summary_statistics"] = {}
            # 3. Missing Values
            missing = df.isnull().sum()
            missing_percent = (missing / len(df)) * 100
            report["missing_values"] = {
                col: {"count": int(missing[col]), "percent": float(missing_percent[col])}
                for col in df.columns if missing[col] > 0
            }
            # 4. Unique values
            report['unique_values'] = {col: df[col].nunique() for col in df.columns}
            # 5. Duplicate Rows
            duplicates = df[df.duplicated()]
            report['duplicate_rows_count'] = duplicates.shape[0]
            report['sample_duplicate_rows'] = duplicates.head().to_dict(orient='records')
            # 6. Correlation Matrix (Only numerical)
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                # Select numeric columns from DataFrame and compute correlation
                numeric_df = df[numeric_cols]
                report['correlation_matrix'] = numeric_df.corr(method="pearson").round(3).to_dict()
            else:
                report['correlation_matrix'] = {}
            # 7. Distribution Stats
            distribution_stats = {}
            for col in numeric_cols:
                series = df[col].dropna()
                if len(series) > 0:
                    distribution_stats[col] = {
                        "mean": float(series.mean()) if not np.isnan(series.mean()) else None,
                        "median": float(series.median()) if not np.isnan(series.median()) else None,
                        "std": float(series.std()) if not np.isnan(series.std()) else None,
                        "min": float(series.min()) if not np.isnan(series.min()) else None,
                        "max": float(series.max()) if not np.isnan(series.max()) else None,
                        "skew": float(series.skew()) if not np.isnan(series.skew()) else None,
                        "kurtosis": float(series.kurt()) if not np.isnan(series.kurt()) else None
                    }
            report['distribution_statistics'] = distribution_stats
            # 8. Categorical value count (top5)
            cat_cols = df.select_dtypes(include='object')
            report['categorical_value_counts'] = {
                col: df[col].value_counts(dropna=False).head(5).to_dict() for col in cat_cols.columns
            }
            # 9. Outlier Detection (IQR)
            outlier_summary = {}
            for col in numeric_cols:
                try:
                    Q1 = df[col].quantile(0.25)
                    Q3 = df[col].quantile(0.75)
                    IQR = Q3 - Q1
                    lower = Q1 - 1.5 * IQR
                    upper = Q3 + 1.5 * IQR
                    outliers = df[(df[col] < lower) | (df[col] > upper)]
                    outlier_summary[col] = {
                        "count": int(outliers.shape[0]),
                        "percent": float((outliers.shape[0] / df.shape[0]) * 100)
                    }
                except Exception:
                    outlier_summary[col] = {"count": 0, "percent": 0.0}
            report['outlier_detection'] = outlier_summary
            # 10. Data Drift
            try:
                from river import drift
                # Simple drift detection on first numeric column if available
                if len(numeric_cols) > 0:
                    first_col = numeric_cols[0]
                    series = df[first_col].dropna()
                    ddm = drift.dummy.DummyDriftDetector(t_0=min(1000, len(series)//2), seed=42)
                    drifts = {
                        "index": [],
                        "value": [],
                        "column_analyzed": first_col
                    }
                    
                    # Iterate over the numeric values
                    for i, val in enumerate(series.iloc[:min(1000, len(series))]):  # Limit to first 1000 values
                        if not np.isnan(val):
                            ddm.update(float(val))
                            if ddm.drift_detected:
                                drifts["index"].append(int(i))
                                drifts["value"].append(float(val))
                    
                    report['data_drift'] = drifts
                else:
                    report['data_drift'] = {"message": "No numeric columns available for drift detection"}
                    
            except ImportError:
                logger.warning("River library not available, skipping drift detection")
                report['data_drift'] = {"message": "River library not installed, drift detection skipped"}
            except Exception as e:
                logger.warning(f"Error in drift detection: {e}")
                report['data_drift'] = {"message": f"Drift detection failed: {str(e)}"}

            logger.info("Bias report generation complete")
        else:
            # Fallback if we couldn't parse with pandas
            report["shape"] = [int(meta.get("row_count", 0)), len(meta.get("columns", []) or [])]
            report["columns"] = meta.get("columns", []) or []
            report["dtypes"] = meta.get("data_types", {}) or {}
            report["memory_usage_MB"] = None
            report["summary_statistics"] = {}
    except Exception as e:
        logger.warning(f"Failed to build bias report: {e}")
    
    # Clean the report to ensure JSON serialization compatibility
    return clean_for_json(report)


    

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
                # Parse new Kafka message format
                task_id = value.get("task_id")
                input_data = value.get("input", {})
                
                user_id = input_data.get("user_id")
                dataset_id = input_data.get("dataset_id")
                target_column_name = input_data.get("target_column_name")
                task_type = input_data.get("task_type")
                
                logger.info(f"Task ID={task_id}")
                logger.info(f"Target column={target_column_name}")
                logger.info(f"Task type={task_type}")
                
                if not user_id or not dataset_id:
                    logger.warning("Missing user_id/dataset_id in event; skipping")
                    continue

                # Extract dataset version from input (if provided)
                dataset_version = input_data.get("dataset_version", "v1")  # Default to v1 for backward compatibility
                
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

                # POST bias report to API (include target_column_name, task_type, and dataset_version)
                saved = post_bias_report(
                    user_id=user_id, 
                    dataset_id=dataset_id, 
                    report=bias_report,
                    target_column_name=target_column_name,
                    task_type=task_type,
                    dataset_version=dataset_version,
                    task_id=task_id
                )
                logger.info(f"Saved bias report: {json.dumps(saved, indent=2, default=str)}")
                
                # Transformation step temporarily disabled to avoid re-trigger loops
                logger.info("Transformation step skipped (temporarily disabled)")

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
