#!/usr/bin/env python3
"""
Manually publish a bias-detection trigger to Kafka (replaces Agentic Core for local tests).

Prerequisites:
  - AutoDW stack running (api + bias-detector + kafka), e.g. autodw/docker-compose.yaml
  - Dataset already uploaded via POST /datasets/upload/{user_id}
  - bias-detector container consuming bias-detection-trigger-events

Usage (from repo root, with venv or inside a container that has aiokafka):

  python scripts/trigger_bias_detection.py \\
    --user-id 555889966 \\
    --dataset-id 1 \\
    --dataset-version v2 \\
    --target-column human_label \\
    --task-type classification

Watch bias-detector logs:
  docker logs -f autodw-bias-detector

Verify after run:
  GET http://localhost:8000/bias-reports/{user_id}/{dataset_id}
  Kafka topic bias-detection-complete-events (if task_id was set)
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
logger = logging.getLogger("trigger_bias_detection")

DEFAULT_KAFKA = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_TOPIC = os.getenv("KAFKA_BIAS_TRIGGER_TOPIC", "bias-detection-trigger-events")
DEFAULT_API = os.getenv("API_BASE", "http://localhost:8000")


def _preflight_dataset(api_base: str, user_id: str, dataset_id: str, version: str | None) -> dict:
    if version:
        url = f"{api_base.rstrip('/')}/datasets/{user_id}/{dataset_id}/version/{version}"
    else:
        url = f"{api_base.rstrip('/')}/datasets/{user_id}/{dataset_id}"
    logger.info("Checking dataset metadata: %s", url)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    meta = r.json()
    logger.info(
        "Dataset OK: version=%s is_folder=%s split=%s columns=%s",
        meta.get("version"),
        meta.get("is_folder"),
        (meta.get("custom_metadata") or {}).get("split"),
        meta.get("columns"),
    )
    return meta


def build_trigger_payload(
    *,
    user_id: str,
    dataset_id: str,
    dataset_version: str,
    target_column_name: str,
    task_type: str,
    task_id: str | None,
) -> dict:
    tid = task_id or f"manual-bias-{uuid.uuid4().hex[:12]}"
    return {
        "task_id": tid,
        "event_type": "bias-detection-trigger",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "input": {
            "user_id": user_id,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "target_column_name": target_column_name,
            "task_type": task_type,
        },
    }


async def publish_trigger(
    *,
    bootstrap_servers: str,
    topic: str,
    payload: dict,
) -> None:
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
        logger.info("Trigger sent (task_id=%s). Watch: docker logs -f autodw-bias-detector", task_id)
    finally:
        await producer.stop()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish bias-detection-trigger-events to Kafka")
    p.add_argument("--user-id", required=True, help="Dataset owner user_id")
    p.add_argument("--dataset-id", required=True, help="Dataset id")
    p.add_argument(
        "--dataset-version",
        default="v2",
        help="Version to analyze (default v2 — split datasets use v2 after upload)",
    )
    p.add_argument("--target-column", required=True, help="Label/target column for mitigation & downstream ML")
    p.add_argument(
        "--task-type",
        default="classification",
        choices=["classification", "regression"],
        help="Task type passed to bias detector",
    )
    p.add_argument("--task-id", default=None, help="Optional task_id (enables bias-complete Kafka event)")
    p.add_argument("--kafka", default=DEFAULT_KAFKA, help=f"Bootstrap servers (default {DEFAULT_KAFKA})")
    p.add_argument("--topic", default=DEFAULT_TOPIC, help=f"Trigger topic (default {DEFAULT_TOPIC})")
    p.add_argument("--api-base", default=DEFAULT_API, help=f"AutoDW API for preflight (default {DEFAULT_API})")
    p.add_argument("--skip-preflight", action="store_true", help="Skip GET dataset metadata check")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not args.skip_preflight:
            _preflight_dataset(args.api_base, args.user_id, args.dataset_id, args.dataset_version)
    except requests.RequestException as e:
        logger.error("Preflight failed (is API up at %s?): %s", args.api_base, e)
        return 1

    payload = build_trigger_payload(
        user_id=args.user_id,
        dataset_id=args.dataset_id,
        dataset_version=args.dataset_version,
        target_column_name=args.target_column,
        task_type=args.task_type,
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
        "  - docker logs -f autodw-bias-detector\n"
        "  - curl %s/bias-reports/%s/%s\n"
        "  - If mitigated: note new version in logs / GET dataset versions",
        args.api_base,
        args.user_id,
        args.dataset_id,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
