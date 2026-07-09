from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from ..core.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs/xai", tags=["xai-jobs"])

_index_ready = False


def _normalize_report_type(report_type: Optional[str]) -> str:
    value = (report_type or "model_explanation").strip().lower().replace("-", "_")
    if value in {"data_explanation", "data", "analyze_data", "driver_data"}:
        return "data_explanation"
    return "model_explanation"


def build_xai_job_key(
    *,
    user_id: str,
    dataset_id: str,
    dataset_version: Optional[str],
    model_id: Optional[str],
    model_version: Optional[str],
    report_type: Optional[str],
    level: Optional[str],
    job_key: Optional[str] = None,
) -> str:
    if job_key:
        return job_key
    return "|".join([
        user_id,
        dataset_id,
        dataset_version or "v1",
        model_id or "",
        model_version or "v1",
        _normalize_report_type(report_type),
        level or "beginner",
    ])


async def _ensure_indexes() -> None:
    global _index_ready
    if _index_ready:
        return
    db = get_database()
    await db.xai_job_locks.create_index("task_id", unique=True)
    await db.xai_job_locks.create_index("job_key", unique=True)
    _index_ready = True


class XaiJobClaimRequest(BaseModel):
    task_id: str = Field(..., description="Kafka task_id (idempotency key)")
    job_key: Optional[str] = Field(
        None,
        description="Stable dedup key: user|dataset|version|model|version|report_type|level",
    )
    user_id: str
    dataset_id: str
    dataset_version: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None
    report_type: Optional[str] = Field(
        None,
        description="model_explanation or data_explanation",
    )
    level: Optional[str] = None


class XaiJobClaimResponse(BaseModel):
    task_id: str
    job_key: str
    claimed: bool
    claimed_at: str


@router.post("/claim", response_model=XaiJobClaimResponse)
async def claim_xai_job(payload: XaiJobClaimRequest) -> XaiJobClaimResponse:
    """
    Idempotency guard for XAI triggers.

    With multiple XAI consumer replicas, at-least-once delivery can cause duplicates.
    This endpoint ensures only ONE worker proceeds for a given task_id OR job_key.

    job_key dedupes orchestrator retries that reuse the same dataset/model/report_type
    but assign a new task_id (common when model and data are separate triggers).
    """
    await _ensure_indexes()
    db = get_database()
    now = datetime.now(tz=timezone.utc).isoformat()
    resolved_job_key = build_xai_job_key(
        user_id=payload.user_id,
        dataset_id=payload.dataset_id,
        dataset_version=payload.dataset_version,
        model_id=payload.model_id,
        model_version=payload.model_version,
        report_type=payload.report_type,
        level=payload.level,
        job_key=payload.job_key,
    )
    doc = {
        "task_id": payload.task_id,
        "job_key": resolved_job_key,
        "user_id": payload.user_id,
        "dataset_id": payload.dataset_id,
        "dataset_version": payload.dataset_version,
        "model_id": payload.model_id,
        "model_version": payload.model_version,
        "report_type": _normalize_report_type(payload.report_type),
        "level": payload.level or "beginner",
        "claimed_at": now,
    }
    try:
        await db.xai_job_locks.insert_one(doc)
        return XaiJobClaimResponse(
            task_id=payload.task_id,
            job_key=resolved_job_key,
            claimed=True,
            claimed_at=now,
        )
    except DuplicateKeyError:
        existing = await db.xai_job_locks.find_one(
            {"$or": [{"task_id": payload.task_id}, {"job_key": resolved_job_key}]},
            projection={"task_id": 1, "job_key": 1},
        )
        detail = "task_id or job_key already claimed"
        if existing:
            if existing.get("task_id") == payload.task_id:
                detail = "task_id already claimed"
            elif existing.get("job_key") == resolved_job_key:
                detail = "job_key already claimed"
        raise HTTPException(status_code=409, detail=detail)
    except Exception as e:
        logger.error("Failed to claim xai job: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to claim xai job")
