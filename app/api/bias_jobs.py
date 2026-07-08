from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from ..core.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs/bias", tags=["bias-jobs"])

_index_ready = False


async def _ensure_indexes() -> None:
    global _index_ready
    if _index_ready:
        return
    db = get_database()
    await db.bias_job_locks.create_index("task_id", unique=True)
    _index_ready = True


class BiasJobClaimRequest(BaseModel):
    task_id: str = Field(..., description="Kafka task_id (idempotency key)")
    user_id: str
    dataset_id: str
    dataset_version: Optional[str] = None


class BiasJobClaimResponse(BaseModel):
    task_id: str
    claimed: bool
    claimed_at: str


@router.post("/claim", response_model=BiasJobClaimResponse)
async def claim_bias_job(payload: BiasJobClaimRequest) -> BiasJobClaimResponse:
    """
    Idempotency guard for bias-detection triggers.

    With multiple bias-detector replicas, at-least-once delivery can cause duplicates.
    This endpoint ensures only ONE worker proceeds for a given task_id.
    """
    await _ensure_indexes()
    db = get_database()
    now = datetime.now(tz=timezone.utc).isoformat()
    doc = {
        "task_id": payload.task_id,
        "user_id": payload.user_id,
        "dataset_id": payload.dataset_id,
        "dataset_version": payload.dataset_version,
        "claimed_at": now,
    }
    try:
        await db.bias_job_locks.insert_one(doc)
        return BiasJobClaimResponse(task_id=payload.task_id, claimed=True, claimed_at=now)
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="task_id already claimed")
    except Exception as e:
        logger.error("Failed to claim bias job: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to claim bias job")

