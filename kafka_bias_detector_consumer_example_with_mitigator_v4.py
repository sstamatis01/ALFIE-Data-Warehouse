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
from sklearn.preprocessing import LabelEncoder, PowerTransformer, StandardScaler
from scipy.stats import skew, ks_2samp
from imblearn.over_sampling import SMOTE
from sklearn.utils.multiclass import type_of_target

from app.services.transformation_report_service import transformation_report_service

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
            # 1. Basic info
            report["target_column"] = meta.get("target_column_name")
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
            missing_percent = missing.sort_values(ascending=False).iloc[0] / len(df)
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
            if not numeric_cols.empty:
                report['correlation_matrix'] = numeric_cols.corr(method="pearson").round(3).to_dict(orient='records')
            # 7. Distribution Stats
            distribution_stats = {}
            for col in numeric_cols.columns:
                series = df[col].dropna()
                distribution_stats[col] = {
                    "mean": series.mean(),
                    "median": series.median(),
                    "std": series.std(),
                    "min": series.min(),
                    "max": series.max(),
                    "skew": series.skew(),
                    "kurtosis": series.kurt()
                }
            report['distribution_statistics'] = distribution_stats
            # 8. Categorical value count (top5)
            cat_cols = df.select_dtypes(include='object')
            report['categorical_value_counts'] = {
                col: df[col].value_counts(dropna=False).head(5).to_dict() for col in cat_cols.columns
            }
            # 9. Outliner Detection (IQR)
            outlier_summary = {}
            for col in numeric_cols.columns:
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower = Q1 - 1.5 * IQR
                upper = Q3 + 1.5 * IQR
                outliers = df[(df[col] < lower) | (df[col] > upper)]
                outlier_summary[col] = {
                    "count": outliers.shape[0],
                    "percent": (outliers.shape[0] / df.shape[0]) * 100
                }
            report['outlier_detection'] = outlier_summary
            # 10. Data Drift
            datastream = iter(df)
            # Initialise the DDM
            from river import drift
            ddm = drift.dummy.DummyDriftDetector(t_0=1000, seed=42)
            drifts = {
                "index": [],
                "value": [],
            }

            # Iterate over the data stream
            for i, val in enumerate(datastream):
                ddm.update(val)
                if ddm.drift_detected:
                    print(f"Change detected at index {i}, input value: {val}")
                    drifts["index"].append(i)
                    drifts["value"].append(val)

            report['data_drift'] = drifts

            print("\n Detector Complete!")
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


def preprocess_data(df: pd.DataFrame, eda_results: dict):
    df_cleaned = df.copy()
    target_column = eda_results.get("target_column")
    transformation_log = []
    try:
        # 1. Fill missing values
        for col in eda_results.get("columns", df_cleaned.columns):
            if col not in df_cleaned.columns:
                continue
            nulls = int(df_cleaned[col].isnull().sum())
            if nulls > 0:
                is_numeric = pd.api.types.is_numeric_dtype(df_cleaned[col])
                method = "median" if is_numeric else "mode"
                fill_value = df_cleaned[col].median() if method == "median" else df_cleaned[col].mode().iloc[0]
                df_cleaned[col] = df_cleaned[col].fillna(fill_value)

                transformation_log.append({
                    "column": col,
                    "transformation": "missing_value_fill",
                    "method": method,
                    "original_missing_values": f"{nulls} missing",
                    "modified_value": fill_value
                })

        # 2. Remove duplicates
        dup_count = int(eda_results.get("duplicate_rows_count", df_cleaned.duplicated().sum()))
        if dup_count > 0:
            df_cleaned = df_cleaned.drop_duplicates()
            transformation_log.append({
                "column": "all",
                "transformation": "duplicate_removal",
                "method": "drop_duplicates",
                "original_value": f"{dup_count} duplicates",
                "modified_value": "duplicates removed"
            })

        # 3. Encode categorical features
        cat_cols = df_cleaned.select_dtypes(include='object').columns
        for col in cat_cols:
            if col == target_column:
                # Keep classification labels as-is for now; optionally label-encode below after task inference
                continue
            unique_vals = df_cleaned[col].nunique(dropna=True)
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
                    'original_value': int(unique_vals),
                    'modified_value': f"integers from 0 to {unique_vals - 1}"
                })

        # Infer task type (classification vs regression) if target exists
        task_type = "unknown"
        y = None
        y_type = None

        if target_column is not None and target_column in df_cleaned.columns:
            y = df_cleaned[target_column]

            # If target is object/categorical, label-encode so type_of_target works cleanly
            if pd.api.types.is_object_dtype(y) or pd.api.types.is_categorical_dtype(y):
                le_y = LabelEncoder()
                df_cleaned[target_column] = le_y.fit_transform(y.astype(str))
                y = df_cleaned[target_column]
                transformation_log.append({
                    "column": target_column,
                    "transformation": "target_encoding",
                    "method": "label_encoding",
                    "original_value": "object/categorical labels",
                    "modified_value": f"integers from 0 to {int(pd.Series(y).nunique()) - 1}"
                })

            y_type = type_of_target(y)

            if y_type in {"binary", "multiclass"}:
                task_type = "classification"
            elif y_type == "continuous":
                task_type = "regression"
            else:
                # multilabel, continuous-multioutput, etc.
                task_type = "other"

        transformation_log.append({
            "column": target_column if target_column else "unknown",
            "transformation": "task_inference",
            "method": "type_of_target",
            "original_value": str(y_type),
            "modified_value": task_type
        })

        # 4. Handle skewed features (EXCLUDE target)
        numeric_cols = df_cleaned.select_dtypes(include=[np.number]).columns.tolist()
        feature_numeric_cols = [c for c in numeric_cols if c != target_column]
        for col in numeric_cols:
            series = df_cleaned[col].dropna()
            if series.empty:
                continue
            col_skew = skew(df_cleaned[col].dropna())
            if abs(col_skew) > 0.75:
                original_skew = float(col_skew)
                if (df_cleaned[col] > 0).all():
                    transformer = PowerTransformer(method='yeo-johnson')
                    df_cleaned[col] = transformer.fit_transform(df_cleaned[[col]])
                    method = 'yeo-johnson'
                else:
                    scaler = StandardScaler()
                    df_cleaned[col] = scaler.fit_transform(df_cleaned[[col]])
                    method = 'standard_scaler'
                new_skew = float(skew(df_cleaned[col].dropna()))
                transformation_log.append({
                    'column': col,
                    'transformation': 'skew_correction',
                    'method': method,
                    'original_value': round(original_skew, 3),
                    'modified_value': round(new_skew, 3)
                })

        # 5. Classification-only: Oversampling (SMOTE) ONLY when compatible
        if task_type == "classification" and target_column is not None:
            X = df_cleaned.drop(columns=[target_column])
            y = df_cleaned[target_column]

            # Only apply SMOTE for discrete class targets
            if type_of_target(y) in {"binary", "multiclass"}:
                vc = y.value_counts()
                n_classes = y.nunique()
                if n_classes > 8:
                    transformation_log.append({
                        "column": target_column,
                        "transformation": "oversampling_skipped",
                        "method": "SMOTE",
                        "original_value": vc.to_dict(),
                        "modified_value": f"Skipped (too many classes: {n_classes})"
                    })
                else:
                    imbalance_ratio = vc.min() / vc.max() if vc.max() > 0 else 1.0
                    minority_count = int(vc.min())

                    # Extra guard: SMOTE is fragile when rare classes are tiny
                    # Require at least 6 samples in the smallest class for default-like behavior
                    if imbalance_ratio < 0.5 and minority_count >= 2:
                        # dynamically choose k_neighbors so it is always valid
                        k_neighbors = min(5, minority_count - 1)

                        # If the class is too tiny, skip SMOTE rather than creating unstable synthetic points
                        if k_neighbors < 1:
                            transformation_log.append({
                                "column": target_column,
                                "transformation": "oversampling_skipped",
                                "method": "SMOTE",
                                "original_value": vc.to_dict(),
                                "modified_value": f"Skipped (smallest class has {minority_count} sample)"
                            })
                        else:
                            try:
                                smote = SMOTE(random_state=42, k_neighbors=k_neighbors)
                                X_resampled, y_resampled = smote.fit_resample(X, y)

                                transformation_log.append({
                                    "column": target_column,
                                    "transformation": "oversampling",
                                    "method": f"SMOTE(k_neighbors={k_neighbors})",
                                    "original_value": vc.to_dict(),
                                    "modified_value": pd.Series(y_resampled).value_counts().to_dict()
                                })

                                df_cleaned = pd.concat(
                                    [
                                        pd.DataFrame(X_resampled, columns=X.columns),
                                        pd.Series(y_resampled, name=target_column)
                                    ],
                                    axis=1
                                )

                            except ValueError as e:
                                transformation_log.append({
                                    "column": target_column,
                                    "transformation": "oversampling_skipped",
                                    "method": "SMOTE",
                                    "original_value": vc.to_dict(),
                                    "modified_value": f"Skipped due to SMOTE error: {str(e)}"
                                })
                    else:
                        transformation_log.append({
                            "column": target_column,
                            "transformation": "oversampling_skipped",
                            "method": "SMOTE",
                            "original_value": vc.to_dict(),
                            "modified_value": f"Skipped (imbalance_ratio={imbalance_ratio:.3f}, min_class={minority_count})"
                        })
            else:
                transformation_log.append({
                    "column": target_column,
                    "transformation": "oversampling_skipped",
                    "method": "SMOTE",
                    "original_value": str(type_of_target(y)),
                    "modified_value": "Skipped (target not discrete classification labels)"
                })

        # 6. Data drift detection & mitigation (features only)
        for col in numeric_cols:
            series = df_cleaned[col].dropna()
            if series.empty:
                continue

            # Guard against std=0
            std = float(series.std())
            if std == 0 or np.isnan(std):
                continue

            reference = np.random.normal(loc=float(series.mean()), scale=std, size=series.shape[0])
            ks_stat, p_value = ks_2samp(series, reference)

            if p_value < 0.01:
                original_mean = float(series.mean())
                scaler = StandardScaler()
                df_cleaned[col] = scaler.fit_transform(df_cleaned[[col]])
                modified_mean = float(df_cleaned[col].mean())

                transformation_log.append({
                    "column": col,
                    "transformation": "drift_mitigation",
                    "method": "standard_scaler",
                    "original_value": round(original_mean, 3),
                    "modified_value": round(modified_mean, 3)
                })
    except Exception as e:
        logger.warning(f"Failed to build bias report: {e}")
    return df_cleaned, transformation_log


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
                df_transformed, transformation_report = preprocess_data(df, bias_report)

                # Post transformation report to API:
                requests.post(
                    f"{API_BASE}/transformation-reports/",
                    json={
                        "user_id": user_id,
                        "dataset_id": dataset_id,
                        "version": "v2",
                        "report": transformation_report,
                    },
                    timeout=30,
                ).raise_for_status()
                logger.info(f"Saved transformation report: {json.dumps(saved, indent=2, default=str)}")

                # upload v2 dataset
                try:
                    from io import BytesIO
                    buf = BytesIO()
                    df_transformed.to_csv(buf, index=False)
                    buf.seek(0)
                    files = {"file": ("dataset_v2.csv", buf.getvalue(), "text/csv")}
                    dataset_id = +1
                    data = {
                        "user_id": user_id,
                        "dataset_id": dataset_id,
                        "name": meta.get("name", dataset_id),
                        "description": "Mitigated dataset v2",
                        "version": "v2",
                    }

                    requests.post(f"{API_BASE}/datasets/upload", files=files, data=data, timeout=120).raise_for_status()
                    logger.info(f"Saved enhanced dataset as {dataset_id}: {json.dumps(saved, indent=2, default=str)}")
                except Exception as e:
                    logger.warning(f"Could not parse enhanced dataframe as CSV: {e}")

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
