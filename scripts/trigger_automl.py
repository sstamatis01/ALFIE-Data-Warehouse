#!/usr/bin/env python3
"""
Manually publish an AutoML trigger to Kafka (replaces Agentic Core for local tests).

Prerequisites:
  - AutoDW stack running (api + automl-consumer + kafka), e.g. autodw/docker-compose.yaml
  - Mitigated (or raw) dataset version available in DW
  - Tabular AutoML service reachable from automl-consumer (default host.docker.internal:8001)

Usage (from repo root, or inside autodw-api / automl-consumer container):

  python scripts/trigger_automl.py \\
    --user-id 1 \\
    --dataset-id 16504691-8ec9-4028-a72b-2ab993640045 \\
    --dataset-version v3 \\
    --target-column label \\
    --task-type classification \\
    --time-budget 60

Note: time_budget is passed through to the consumer as SECONDS (60 = 1 minute max training).

Watch:
  docker logs -f autodw-automl-consumer

Verify after run:
  GET http://localhost:8000/ai-models/{user_id}
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
logger = logging.getLogger("trigger_automl")

DEFAULT_KAFKA = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_TOPIC = os.getenv("KAFKA_AUTOML_TRIGGER_TOPIC", "automl-trigger-events")
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
    task_category: str,
    time_budget_seconds: int,
    task_id: str | None,
) -> dict:
    tid = task_id or f"manual-automl-{uuid.uuid4().hex[:12]}"
    return {
        "task_id": tid,
        "event_type": "automl-trigger",
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "input": {
            "user_id": user_id,
            "dataset_id": dataset_id,
            "dataset_version": dataset_version,
            "task_category": task_category,
            "target_column_name": target_column_name,
            "task_type": task_type,
            "time_budget": str(time_budget_seconds),
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
        logger.info(
            "Trigger sent (task_id=%s). Watch: docker logs -f autodw-automl-consumer",
            task_id,
        )
    finally:
        await producer.stop()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish automl-trigger-events to Kafka")
    p.add_argument("--user-id", required=True)
    p.add_argument("--dataset-id", required=True)
    p.add_argument(
        "--dataset-version",
        default="v3",
        help="Dataset version for training (default v3 — mitigated after bias step)",
    )
    p.add_argument("--target-column", required=True)
    p.add_argument(
        "--task-type",
        default="classification",
        choices=["classification", "regression", "multiclass", "binary"],
    )
    p.add_argument(
        "--task-category",
        default="tabular",
        choices=["tabular", "vision"],
    )
    p.add_argument(
        "--time-budget",
        type=int,
        default=60,
        metavar="SECONDS",
        help="Training time budget in seconds (default 60 = 1 minute)",
    )
    p.add_argument("--task-id", default=None)
    p.add_argument("--kafka", default=DEFAULT_KAFKA)
    p.add_argument("--topic", default=DEFAULT_TOPIC)
    p.add_argument("--api-base", default=DEFAULT_API)
    p.add_argument("--skip-preflight", action="store_true")
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
        task_category=args.task_category,
        time_budget_seconds=args.time_budget,
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
        "  - docker logs -f autodw-automl-consumer\n"
        "  - curl %s/ai-models/%s\n"
        "  - Kafka topic automl-events (if tabular service uploaded with task_id)",
        args.api_base,
        args.user_id,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
