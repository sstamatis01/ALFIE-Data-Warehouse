#!/usr/bin/env python3
"""
Manually publish an AutoML trigger to Kafka (replaces Agentic Core for local tests).

Prerequisites:
  - AutoDW stack running (api + automl-consumer + kafka), e.g. autodw/docker-compose.yaml
  - Mitigated dataset version in user space (typically v3 after bias step)
  - Tabular AutoML service reachable from automl-consumer (default host.docker.internal:8001)

After public import + bias mitigation:
  - v1/v2 may be public_link only (no user MinIO objects)
  - v3 is user-owned under datasets/{user_id}/{dataset_id}/v3/ — use that for AutoML

Example — german_credit mitigated v3 for user 99:

  docker run --rm --network autodw_autodw-network \\
    -v "%CD%:/work" -w /work \\
    -e KAFKA_BOOTSTRAP_SERVERS=kafka:29092 -e API_BASE=http://api:8000 \\
    gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw:1.0.3 \\
    python scripts/trigger_automl.py --preset german_credit --user-id 99 --wait

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
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("trigger_automl")

DEFAULT_KAFKA = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
DEFAULT_TOPIC = os.getenv("KAFKA_AUTOML_TRIGGER_TOPIC", "automl-trigger-events")
DEFAULT_API = os.getenv("API_BASE", "http://localhost:8000")

# Defaults for summer-school catalog (train on mitigated v3 after bias step)
SUMMER_SCHOOL_PRESETS: dict[str, dict[str, str]] = {
    "german_credit": {
        "dataset_id": "german_credit",
        "dataset_version": "v3",
        "target_column": "credit_risk",
        "task_type": "classification",
        "task_category": "tabular",
    },
    "compas_recidivism": {
        "dataset_id": "compas_recidivism",
        "dataset_version": "v3",
        "target_column": "two_year_recid",
        "task_type": "classification",
        "task_category": "tabular",
    },
    "adult_census_income": {
        "dataset_id": "adult_census_income",
        "dataset_version": "v3",
        "target_column": "income",
        "task_type": "classification",
        "task_category": "tabular",
    },
    "taiwan_credit_default": {
        "dataset_id": "taiwan_credit_default",
        "dataset_version": "v3",
        "target_column": "default_next_month",
        "task_type": "classification",
        "task_category": "tabular",
    },
    "communities_crime": {
        "dataset_id": "communities_crime",
        "dataset_version": "v3",
        "target_column": "ViolentCrimesPerPop",
        "task_type": "regression",
        "task_category": "tabular",
    },
}


def _dataset_url(api_base: str, user_id: str, dataset_id: str, version: str | None) -> str:
    base = api_base.rstrip("/")
    if version:
        return f"{base}/datasets/{user_id}/{dataset_id}/version/{version}"
    return f"{base}/datasets/{user_id}/{dataset_id}"


def preflight_dataset(api_base: str, user_id: str, dataset_id: str, version: str | None) -> dict:
    url = _dataset_url(api_base, user_id, dataset_id, version)
    logger.info("Checking dataset metadata: %s", url)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    meta = r.json()
    tags = [str(t).lower() for t in (meta.get("tags") or [])]
    link = meta.get("public_link")
    split = (meta.get("custom_metadata") or {}).get("split")
    logger.info(
        "Dataset OK: version=%s is_folder=%s split=%s mitigated=%s",
        meta.get("version"),
        meta.get("is_folder"),
        split,
        "mitigated" in tags,
    )
    if link:
        logger.warning(
            "Version %s is a public_link import (storage in datasets/public/). "
            "AutoML should use mitigated v3 instead.",
            meta.get("version"),
        )
    elif "mitigated" in tags:
        logger.info("User-owned mitigated dataset (storage under datasets/%s/%s/%s/)", user_id, dataset_id, meta.get("version"))
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


def _models_for_dataset(models: list[dict], dataset_id: str) -> list[dict]:
    out = []
    for m in models:
        td = m.get("training_dataset") or ""
        if td == dataset_id or dataset_id in str(td):
            out.append(m)
    return out


def wait_for_automl_model(
    api_base: str,
    user_id: str,
    dataset_id: str,
    *,
    timeout_s: int = 600,
    poll_s: float = 5.0,
) -> dict[str, Any]:
    """Poll until an AI model trained on dataset_id appears (or timeout)."""
    url = f"{api_base.rstrip('/')}/ai-models/{user_id}"
    deadline = time.time() + timeout_s
    logger.info("Waiting up to %ss for model on %s (GET %s)...", timeout_s, dataset_id, url)

    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                models = r.json()
                matched = _models_for_dataset(models, dataset_id)
                if matched:
                    latest = sorted(matched, key=lambda m: m.get("created_at", ""), reverse=True)[0]
                    logger.info(
                        "Model found: model_id=%s version=%s framework=%s",
                        latest.get("model_id"),
                        latest.get("version"),
                        latest.get("framework"),
                    )
                    return {"models": matched, "latest": latest}
                logger.debug("No model for %s yet (%d total models for user)", dataset_id, len(models))
        except requests.RequestException as e:
            logger.debug("models poll: %s", e)
        time.sleep(poll_s)

    raise TimeoutError(
        f"Timed out after {timeout_s}s. Check: docker logs autodw-automl-consumer; "
        f"ensure Tabular AutoML is up on host port {os.getenv('TABULAR_AUTOML_PORT', '8001')}; GET {url}"
    )


def apply_preset(args: argparse.Namespace) -> None:
    if not args.preset:
        return
    preset = SUMMER_SCHOOL_PRESETS.get(args.preset)
    if not preset:
        known = ", ".join(sorted(SUMMER_SCHOOL_PRESETS))
        raise SystemExit(f"Unknown preset {args.preset!r}. Known: {known}")
    if not args.dataset_id:
        args.dataset_id = preset["dataset_id"]
    if args.dataset_version == "v3" and preset.get("dataset_version"):
        args.dataset_version = preset["dataset_version"]
    if not args.target_column:
        args.target_column = preset["target_column"]
    if args.task_type == "classification" and preset.get("task_type"):
        args.task_type = preset["task_type"]
    if args.task_category == "tabular" and preset.get("task_category"):
        args.task_category = preset["task_category"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Publish automl-trigger-events to Kafka",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Presets: " + ", ".join(sorted(SUMMER_SCHOOL_PRESETS.keys())),
    )
    p.add_argument("--preset", choices=sorted(SUMMER_SCHOOL_PRESETS.keys()), help="Summer-school catalog defaults (v3 mitigated)")
    p.add_argument("--user-id", required=True)
    p.add_argument("--dataset-id", default=None)
    p.add_argument(
        "--dataset-version",
        default="v3",
        help="Dataset version for training (default v3 — mitigated after bias step)",
    )
    p.add_argument("--target-column", default=None)
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
    p.add_argument("--wait", action="store_true", help="Poll until an AI model appears for this dataset")
    p.add_argument("--wait-timeout", type=int, default=600, help="Seconds for --wait (default 600)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    try:
        apply_preset(args)
    except SystemExit as e:
        logger.error("%s", e)
        return 2

    if not args.dataset_id:
        logger.error("--dataset-id is required (or use --preset)")
        return 2
    if not args.target_column:
        logger.error("--target-column is required (or use --preset)")
        return 2

    try:
        if not args.skip_preflight:
            preflight_dataset(args.api_base, args.user_id, args.dataset_id, args.dataset_version)
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
        "  - Kafka topic automl-complete-events",
        args.api_base,
        args.user_id,
    )

    if args.wait:
        try:
            wait_for_automl_model(
                args.api_base,
                args.user_id,
                args.dataset_id,
                timeout_s=args.wait_timeout,
            )
            logger.info("AutoML step completed.")
        except TimeoutError as e:
            logger.error("%s", e)
            return 1
        except requests.RequestException as e:
            logger.error("Wait/verify failed: %s", e)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
