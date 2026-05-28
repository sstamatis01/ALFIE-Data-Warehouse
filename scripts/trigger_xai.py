#!/usr/bin/env python3
"""
Manually publish an XAI trigger to Kafka (replaces Agentic Core for local tests).

Prerequisites:
  - AutoDW stack running (api + kafka), e.g. autodw/docker-compose.yaml
  - XAI stack running (kafka-xai-consumer + explainability API on :5000 or :5010)
  - Dataset and trained model already in AutoDW

Usage (from repo root, or inside autodw-api container):

  python scripts/trigger_xai.py \\
    --user-id 1 \\
    --dataset-id 16504691-8ec9-4028-a72b-2ab993640045 \\
    --dataset-version v3 \\
    --model-id automl_16504691-8ec9-4028-a72b-2ab993640045_1779290487 \\
    --model-version v1 \\
    --level beginner

Watch:
  docker logs -f xai-kafka-consumer

Verify:
  GET http://localhost:8000/xai-reports/{user_id}/{dataset_id}/{model_id}
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("trigger_xai")

DEFAULT_KAFKA = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_TOPIC = os.getenv("KAFKA_XAI_TRIGGER_TOPIC", "xai-trigger-events")
DEFAULT_API = os.getenv("API_BASE", "http://localhost:8000")


def _preflight(api_base: str, user_id: str, dataset_id: str, dataset_version: str, model_id: str, model_version: str) -> tuple[dict, dict]:
    ds_url = f"{api_base.rstrip('/')}/datasets/{user_id}/{dataset_id}/version/{dataset_version}"
    logger.info("Checking dataset: %s", ds_url)
    ds = requests.get(ds_url, timeout=30)
    ds.raise_for_status()
    ds_meta = ds.json()

    model_url = f"{api_base.rstrip('/')}/ai-models/{user_id}/{model_id}"
    logger.info("Checking model: %s?version=%s", model_url, model_version)
    model = requests.get(model_url, params={"version": model_version}, timeout=30)
    model.raise_for_status()
    model_meta = model.json()

    split = (ds_meta.get("custom_metadata") or {}).get("split")
    file_count = ds_meta.get("file_count")
    if file_count is None:
        file_count = (ds_meta.get("custom_metadata") or {}).get("file_count")
    if file_count is None and split:
        file_count = len(split) if isinstance(split, dict) else None

    logger.info(
        "Dataset OK: version=%s is_folder=%s file_count=%s split=%s",
        ds_meta.get("version"),
        ds_meta.get("is_folder"),
        file_count,
        split,
    )
    logger.info(
        "Model OK: version=%s framework=%s type=%s files=%s",
        model_meta.get("version"),
        model_meta.get("framework"),
        model_meta.get("model_type"),
        len(model_meta.get("files") or []),
    )
    return ds_meta, model_meta


def build_trigger_payload(
    *,
    user_id: str,
    dataset_id: str,
    dataset_version: str,
    model_id: str,
    model_version: str,
    level: str,
    report_type: str,
    is_folder: bool,
    file_count: int,
    is_model_folder: bool,
    model_file_count: int,
    task_id: str | None,
) -> dict:
    tid = task_id or f"manual-xai-{uuid.uuid4().hex[:12]}"
    return {
        "task_id": tid,
        "event_type": "xai-trigger",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "is_folder": is_folder,
        "file_count": file_count,
        "is_model_folder": is_model_folder,
        "model_file_count": model_file_count,
        "input": {
            "user_id": user_id,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "model_id": model_id,
            "model_version": model_version,
            "level": level,
            "report_type": report_type,
        },
    }


async def publish_trigger(*, bootstrap_servers: str, topic: str, payload: dict) -> None:
    from aiokafka import AIOKafkaProducer

    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8") if k else None,
    )
    await producer.start()
    try:
        task_id = payload["task_id"]
        logger.info("Publishing to %s @ %s", topic, bootstrap_servers)
        logger.info("Payload:\n%s", json.dumps(payload, indent=2))
        await producer.send_and_wait(topic, value=payload, key=task_id)
        logger.info("Trigger sent (task_id=%s). Watch: docker logs -f xai-kafka-consumer", task_id)
    finally:
        await producer.stop()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish xai-trigger-events to Kafka")
    p.add_argument("--user-id", required=True)
    p.add_argument("--dataset-id", required=True)
    p.add_argument("--dataset-version", default="v3")
    p.add_argument("--model-id", required=True)
    p.add_argument("--model-version", default="v1")
    p.add_argument("--level", default="beginner", choices=["beginner", "expert"])
    p.add_argument("--report-type", default="lime", help="Passed to XAI consumer (default lime)")
    p.add_argument("--task-id", default=None)
    p.add_argument("--kafka", default=DEFAULT_KAFKA)
    p.add_argument("--topic", default=DEFAULT_TOPIC)
    p.add_argument("--api-base", default=DEFAULT_API)
    p.add_argument("--skip-preflight", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    is_folder = True
    file_count = 3
    is_model_folder = False
    model_file_count = 1

    try:
        if not args.skip_preflight:
            ds_meta, model_meta = _preflight(
                args.api_base,
                args.user_id,
                args.dataset_id,
                args.dataset_version,
                args.model_id,
                args.model_version,
            )
            is_folder = bool(ds_meta.get("is_folder"))
            fc = ds_meta.get("file_count")
            if fc is None:
                fc = (ds_meta.get("custom_metadata") or {}).get("file_count")
            if fc is None and (ds_meta.get("custom_metadata") or {}).get("split"):
                fc = len((ds_meta.get("custom_metadata") or {}).get("split"))
            file_count = int(fc) if fc is not None else 1
            files = model_meta.get("files") or []
            is_model_folder = len(files) > 1
            model_file_count = len(files) if files else 1
    except requests.RequestException as e:
        logger.error("Preflight failed (is API up at %s?): %s", args.api_base, e)
        return 1

    payload = build_trigger_payload(
        user_id=args.user_id,
        dataset_id=args.dataset_id,
        dataset_version=args.dataset_version,
        model_id=args.model_id,
        model_version=args.model_version,
        level=args.level,
        report_type=args.report_type,
        is_folder=is_folder,
        file_count=file_count,
        is_model_folder=is_model_folder,
        model_file_count=model_file_count,
        task_id=args.task_id,
    )

    try:
        asyncio.run(
            publish_trigger(
                bootstrap_servers=args.kafka,
                topic=args.topic,
                payload=payload,
            )
        )
    except Exception as e:
        logger.error("Failed to publish trigger: %s", e, exc_info=True)
        return 1

    logger.info(
        "Next checks:\n"
        "  - docker logs -f xai-kafka-consumer\n"
        "  - curl %s/xai-reports/%s/%s/%s",
        args.api_base,
        args.user_id,
        args.dataset_id,
        args.model_id,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
