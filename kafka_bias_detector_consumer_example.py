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
from datetime import datetime, timezone

import numpy as np
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
import requests
import pandas as pd
from sklearn.preprocessing import LabelEncoder, PowerTransformer, StandardScaler
from scipy.stats import skew, ks_2samp
from imblearn.over_sampling import SMOTE

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("kafka_consumer_example")

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_BIAS_TRIGGER_TOPIC = os.getenv("KAFKA_BIAS_TRIGGER_TOPIC", "bias-detection-trigger-events")
KAFKA_BIAS_TRIGGER_CONSUMER_GROUP = os.getenv("KAFKA_BIAS_TRIGGER_CONSUMER_GROUP", "bias-trigger-consumer")
KAFKA_BIAS_TOPIC = os.getenv("KAFKA_BIAS_TOPIC", "bias-detection-complete-events")

# Use Docker service name if KAFKA_BOOTSTRAP_SERVERS points to kafka:29092, otherwise use localhost
if "kafka:" in KAFKA_BOOTSTRAP_SERVERS:
    API_BASE = os.getenv("API_BASE", "http://api:8000")
else:
    API_BASE = os.getenv("API_BASE", "http://localhost:8000")


def fetch_dataset_metadata(user_id: str, dataset_id: str, version: str = None) -> dict:
    """Fetch dataset metadata (specific version or latest)"""
    if version:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/version/{version}"
    else:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def download_dataset_file(user_id: str, dataset_id: str, version: str = None) -> bytes:
    """Download dataset file (specific version or latest)"""
    if version:
        url = f"{API_BASE}/datasets/{user_id}/{dataset_id}/version/{version}/download"
    else:
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
<<<<<<< HEAD
    """
    Post bias report to API
    
    Note: If task_id is None, the API will not send the bias-complete event.
    This allows us to delay the event until after mitigation completes.
    """
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


<<<<<<< HEAD
async def send_bias_complete_event(
    producer: AIOKafkaProducer,
    task_id: str,
    user_id: str,
    dataset_id: str,
    dataset_version: str,
    bias_report_id: str,
    mitigated_dataset_version: str | None = None,
    transformation_report_id: str | None = None,
    success: bool = True,
    error_message: str | None = None
) -> None:
    """Send bias detection completion event with mitigation metadata"""
    if not producer:
        logger.warning("Kafka producer not initialized; skipping bias completion event")
        return
    
    payload = {
        "task_id": task_id,
        "event_type": "bias-detection-complete",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    
    if success:
        output = {
            "bias_report_id": bias_report_id,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "user_id": user_id
        }
        # Add mitigation metadata if available
        if mitigated_dataset_version:
            output["mitigated_dataset_version"] = mitigated_dataset_version
        if transformation_report_id:
            output["transformation_report_id"] = transformation_report_id
        
        payload["output"] = output
        payload["failure"] = None
    else:
        payload["output"] = None
        payload["failure"] = {
            "error_type": "BiasDetectionError",
            "error_message": error_message or "Bias detection failed"
        }
    
    try:
        await producer.send_and_wait(KAFKA_BIAS_TOPIC, value=payload, key=task_id)
        logger.info(f"✅ Bias completion event sent for task_id={task_id}")
        if mitigated_dataset_version:
            logger.info(f"   Includes mitigation info: version={mitigated_dataset_version}, report_id={transformation_report_id}")
    except Exception as e:
        logger.error(f"❌ Failed to send bias completion event: {e}", exc_info=True)


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


def preprocess_data(df: pd.DataFrame, eda_results: dict):
    """
    Apply bias mitigation transformations to the dataset
    
    Returns:
        tuple: (transformed_dataframe, transformation_log)
    """
    df_cleaned = df.copy()
    transformation_log = []
    try:
        # 1. Fill missing values
        for col in eda_results.get("columns", df_cleaned.columns):
            if col in df_cleaned.columns and df_cleaned[col].isnull().sum() > 0:
                method = 'median' if df_cleaned[col].dtype in [np.float64, np.int64] else 'mode'
                original_null_count = int(df_cleaned[col].isnull().sum())
                fill_value = df_cleaned[col].median() if method == 'median' else df_cleaned[col].mode().iloc[0] if len(df_cleaned[col].mode()) > 0 else None
                if fill_value is not None:
                    df_cleaned[col] = df_cleaned[col].fillna(fill_value)
                    transformation_log.append({
                        'column': col,
                        'transformation': 'missing_value_fill',
                        'method': method,
                        'original_missing_values': f"{original_null_count} missing",
                        'modified_value': str(fill_value)
                    })

        # 2. Remove duplicates
        if eda_results.get('duplicate_rows_count', 0) > 0:
            original_count = len(df_cleaned)
            df_cleaned = df_cleaned.drop_duplicates()
            removed_count = original_count - len(df_cleaned)
            if removed_count > 0:
                transformation_log.append({
                    'column': 'all',
                    'transformation': 'duplicate_removal',
                    'method': 'drop_duplicates',
                    'original_value': f"{eda_results['duplicate_rows_count']} duplicates",
                    'modified_value': f"{removed_count} duplicates removed"
                })

        # 3. Encode categorical features
        cat_cols = df_cleaned.select_dtypes(include='object').columns
        for col in cat_cols:
            unique_vals = df_cleaned[col].nunique()
            if unique_vals <= 10:
                dummies = pd.get_dummies(df_cleaned[col], prefix=col)
                df_cleaned = pd.concat([df_cleaned.drop(columns=col), dummies], axis=1)
                transformation_log.append({
                    'column': col,
                    'transformation': 'encoding',
                    'method': 'one-hot',
                    'original_value': unique_vals,
                    'modified_value': f"{dummies.shape[1]} binary columns"
                })
            else:
                le = LabelEncoder()
                df_cleaned[col] = le.fit_transform(df_cleaned[col].astype(str))
                transformation_log.append({
                    'column': col,
                    'transformation': 'encoding',
                    'method': 'label_encoding',
                    'original_value': unique_vals,
                    'modified_value': f"integers from 0 to {unique_vals - 1}"
                })

        # 4. Handle skewed features
        numeric_cols = df_cleaned.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            col_skew = skew(df_cleaned[col].dropna())
            if abs(col_skew) > 0.75:
                original_skew = col_skew
                if (df_cleaned[col] > 0).all():
                    transformer = PowerTransformer(method='yeo-johnson')
                    df_cleaned[col] = transformer.fit_transform(df_cleaned[[col]])
                    method = 'yeo-johnson'
                else:
                    scaler = StandardScaler()
                    df_cleaned[col] = scaler.fit_transform(df_cleaned[[col]])
                    method = 'standard_scaler'
                new_skew = skew(df_cleaned[col])
                transformation_log.append({
                    'column': col,
                    'transformation': 'skew_correction',
                    'method': method,
                    'original_value': round(original_skew, 3),
                    'modified_value': round(new_skew, 3)
                })

        # 5. Oversampling for target if detected
        target_col = None
        for col, stats in eda_results.get("distribution_statistics", {}).items():
            if abs(stats.get("skew", 0)) > 0.75 and col in df_cleaned.columns:
                target_col = col
                break

        if target_col and df_cleaned[target_col].nunique() == 2:
            X = df_cleaned.drop(columns=[target_col])
            y = df_cleaned[target_col]
            smote = SMOTE(random_state=42)
            X_resampled, y_resampled = smote.fit_resample(X, y)
            transformation_log.append({
                'column': target_col,
                'transformation': 'oversampling',
                'method': 'SMOTE',
                'original_value': df_cleaned[target_col].value_counts().to_dict(),
                'modified_value': pd.Series(y_resampled).value_counts().to_dict()
            })
            df_cleaned = pd.concat([pd.DataFrame(X_resampled, columns=X.columns), pd.Series(y_resampled, name=target_col)], axis=1)

        # 6. Data drift detection and mitigation
        numeric_cols = df_cleaned.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            series = df_cleaned[col].dropna()
            if len(series) > 0:
                reference = np.random.normal(loc=series.mean(), scale=series.std(), size=min(series.shape[0], 1000))
                ks_stat, p_value = ks_2samp(series.iloc[:min(1000, len(series))], reference)
                if p_value < 0.01:
                    original_mean = series.mean()
                    scaler = StandardScaler()
                    df_cleaned[col] = scaler.fit_transform(df_cleaned[[col]])
                    modified_mean = df_cleaned[col].mean()
                    transformation_log.append({
                        'column': col,
                        'transformation': 'drift_mitigation',
                        'method': 'standard_scaler',
                        'original_value': round(original_mean, 3),
                        'modified_value': round(modified_mean, 3)
                    })
    except Exception as e:
        logger.warning(f"Error in preprocessing: {e}")
    
    return df_cleaned, transformation_log


def upload_mitigated_dataset(user_id: str, original_dataset_id: str, original_version: str,
                              df_transformed: pd.DataFrame, meta: dict) -> dict:
    """
    Upload mitigated dataset as a new version with flag to prevent re-processing
    
    Returns:
        dict: Response from the upload endpoint, which includes the actual version assigned by the API
    """
    from io import BytesIO
    
    # Convert DataFrame to CSV bytes
    buf = BytesIO()
    df_transformed.to_csv(buf, index=False)
    buf.seek(0)
    csv_bytes = buf.getvalue()
    
    # Upload the mitigated dataset - let the API auto-detect the next version
    # The API will automatically increment the version (v1 -> v2 -> v3, etc.)
    url = f"{API_BASE}/datasets/upload/{user_id}"
    files = {"file": (f"{original_dataset_id}_mitigated.csv", csv_bytes, "text/csv")}
    
    # Combine existing tags with mitigation tags
    existing_tags = meta.get("tags", [])
    if isinstance(existing_tags, str):
        existing_tags = [t.strip() for t in existing_tags.split(",") if t.strip()]
    mitigation_tags = existing_tags + ["mitigated", "bias-corrected"]
    
    data = {
        "dataset_id": original_dataset_id,  # Same dataset_id, different version (auto-incremented by API)
        "name": f"{meta.get('name', original_dataset_id)} (Mitigated)",
        "description": f"Bias-mitigated version of {original_dataset_id} {original_version}. Generated automatically by bias mitigation process.",
        "tags": ",".join(mitigation_tags)
    }
    
    response = requests.post(url, files=files, data=data, timeout=120)
    response.raise_for_status()
    result = response.json()
    
    # Extract the actual version from the API response
    actual_version = result.get("version", "v1")
    logger.info(f"Mitigated dataset uploaded successfully")
    logger.info(f"  Dataset ID: {original_dataset_id}")
    logger.info(f"  Actual version assigned by API: {actual_version}")
    logger.info(f"  Original version: {original_version}")
    logger.info(f"  Tagged with 'mitigated' to prevent re-processing")
    
    return result


async def run_consumer() -> None:
    # Initialize Kafka producer for sending completion events
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda x: json.dumps(x, default=str).encode('utf-8'),
        key_serializer=lambda x: x.encode('utf-8') if x else None,
    )
    await producer.start()
    logger.info("Kafka producer started for sending completion events")
    
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
                meta = fetch_dataset_metadata(user_id, dataset_id, dataset_version)

                file_bytes = download_dataset_file(user_id, dataset_id, dataset_version)

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

                # POST bias report to API WITHOUT task_id initially (so no event is sent)
                # We'll send the event manually after mitigation completes
                saved = post_bias_report(
                    user_id=user_id, 
                    dataset_id=dataset_id, 
                    report=bias_report,
                    target_column_name=target_column_name,
                    task_type=task_type,
                    dataset_version=dataset_version,
                    task_id=None  # Don't send task_id yet - delay event until after mitigation
                )
                bias_report_id = saved.get("id", "")
                logger.info(f"✅ Bias report saved (ID: {bias_report_id})")
                logger.info(f"   Event will be sent after mitigation completes (if needed)")
                
                # Check if mitigator should run (only if dataset is not already mitigated)
                is_mitigated = meta.get("custom_metadata", {}).get("is_mitigated", False)
                tags = meta.get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                has_mitigated_tag = "mitigated" in [tag.lower() for tag in tags]
                
                # Check if there are issues that need mitigation
                has_missing_values = len(bias_report.get("missing_values", {})) > 0
                has_duplicates = bias_report.get("duplicate_rows_count", 0) > 0
                # Check for skewed distributions (abs(skew) > 0.75)
                has_skewed_cols = any(
                    abs(stats.get("skew", 0)) > 0.75 
                    for stats in bias_report.get("distribution_statistics", {}).values()
                )
                needs_mitigation = has_missing_values or has_duplicates or has_skewed_cols
                
                # Variables to track mitigation results
                mitigated_dataset_version = None
                transformation_report_id = None
                
                if not is_mitigated and not has_mitigated_tag and df is not None and needs_mitigation:
                    # Run bias mitigation
                    logger.info("=" * 80)
                    logger.info("Running bias mitigation transformations...")
                    logger.info("=" * 80)
                    
                    try:
                        df_transformed, transformation_log = preprocess_data(df, bias_report)
                        
                        if transformation_log:
                            logger.info(f"Applied {len(transformation_log)} transformations")
                            
                            # Upload mitigated dataset FIRST to get the actual version from the API
                            logger.info("Uploading mitigated dataset...")
                            mitigated_result = upload_mitigated_dataset(
                                user_id=user_id,
                                original_dataset_id=dataset_id,
                                original_version=dataset_version,
                                df_transformed=df_transformed,
                                meta=meta
                            )
                            
                            # Extract the ACTUAL version from the upload response
                            actual_mitigated_version = mitigated_result.get("version")
                            if not actual_mitigated_version:
                                logger.error("Upload response missing version field!")
                                logger.error(f"Response: {json.dumps(mitigated_result, indent=2, default=str)}")
                                raise ValueError("Failed to get version from dataset upload response")
                            
                            mitigated_dataset_version = actual_mitigated_version
                            
                            logger.info(f"✅ Mitigated dataset uploaded successfully!")
                            logger.info(f"   Dataset ID: {dataset_id}")
                            logger.info(f"   Actual mitigated version: {actual_mitigated_version}")
                            logger.info(f"   Original version: {dataset_version}")
                            logger.info(f"   Transformations applied: {len(transformation_log)}")
                            
                            # Post transformation report with the ACTUAL version from upload response
                            transform_url = f"{API_BASE}/transformation-reports/"
                            transform_payload = {
                                "user_id": user_id,
                                "dataset_id": dataset_id,
                                "version": actual_mitigated_version,  # Use actual version from upload
                                "report": transformation_log
                            }
                            transform_resp = requests.post(transform_url, json=transform_payload, timeout=30)
                            transform_resp.raise_for_status()
                            transform_report_result = transform_resp.json()
                            transformation_report_id = transform_report_result.get("id", "")
                            
                            logger.info(f"✅ Transformation report saved successfully!")
                            logger.info(f"   Dataset ID: {dataset_id}")
                            logger.info(f"   Version: {actual_mitigated_version}")
                            logger.info(f"   Transformation report ID: {transformation_report_id}")
                            
                            # Update bias report with mitigation metadata
                            mitigation_metadata = {
                                "mitigation_performed": True,
                                "mitigated_dataset_version": actual_mitigated_version,
                                "transformation_report_id": transformation_report_id,
                                "transformation_count": len(transformation_log)
                            }
                            
                            # Add mitigation metadata to the bias report
                            updated_bias_report = bias_report.copy()
                            updated_bias_report["mitigation"] = mitigation_metadata
                            
                            # Update the bias report by posting again (upsert)
                            updated_saved = post_bias_report(
                                user_id=user_id,
                                dataset_id=dataset_id,
                                report=updated_bias_report,
                                target_column_name=target_column_name,
                                task_type=task_type,
                                dataset_version=dataset_version,
                                task_id=None  # Still no task_id - we'll send event manually
                            )
                            logger.info(f"✅ Bias report updated with mitigation metadata")
                        else:
                            logger.info("No transformations needed - dataset is already clean")
                    except Exception as e:
                        logger.error(f"Error in bias mitigation: {e}", exc_info=True)
                        logger.warning("Continuing without mitigation...")
                else:
                    if is_mitigated or has_mitigated_tag:
                        logger.info("Dataset is already mitigated - skipping mitigation step")
                    elif df is None:
                        logger.info("No DataFrame available - skipping mitigation step")
                    elif not needs_mitigation:
                        logger.info("No bias issues detected that require mitigation - skipping mitigation step")
                
                # Send bias-complete event AFTER all processing (including mitigation) is done
                if task_id:
                    await send_bias_complete_event(
                        producer=producer,
                        task_id=task_id,
                        user_id=user_id,
                        dataset_id=dataset_id,
                        dataset_version=dataset_version,
                        bias_report_id=bias_report_id,
                        mitigated_dataset_version=mitigated_dataset_version,
                        transformation_report_id=transformation_report_id,
                        success=True
                    )
                else:
                    logger.warning("No task_id provided - bias-complete event will not be sent")

            except Exception as proc_err:
                logger.error(f"Processing error: {proc_err}", exc_info=True)
                # Send failure event if task_id is available
                try:
                    task_id = value.get("task_id") if 'value' in locals() else None
                    if task_id:
                        await send_bias_complete_event(
                            producer=producer,
                            task_id=task_id,
                            user_id=value.get("input", {}).get("user_id", "unknown") if 'value' in locals() else "unknown",
                            dataset_id=value.get("input", {}).get("dataset_id", "unknown") if 'value' in locals() else "unknown",
                            dataset_version=value.get("input", {}).get("dataset_version", "v1") if 'value' in locals() else "v1",
                            bias_report_id="",
                            mitigated_dataset_version=None,
                            transformation_report_id=None,
                            success=False,
                            error_message=str(proc_err)
                        )
                except Exception as event_err:
                    logger.error(f"Failed to send failure event: {event_err}")

    
    finally:
        await consumer.stop()
        await producer.stop()
        logger.info("Consumer and producer stopped")


if __name__ == "__main__":
    try:
        asyncio.run(run_consumer())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
