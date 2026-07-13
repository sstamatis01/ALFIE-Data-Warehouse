from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from ..core.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs/concept-drift", tags=["concept-drift-jobs"])

_index_ready = False

HEARTBEAT_FRESH_SECONDS = int(os.getenv("CONCEPT_DRIFT_JOB_LOCK_HEARTBEAT_FRESH_SECONDS", "120"))
STALE_LOCK_SECONDS = int(os.getenv("CONCEPT_DRIFT_JOB_LOCK_STALE_SECONDS", "300"))


def build_concept_drift_job_key(
    *,
    user_id: str,
    dataset_id: str,
    dataset_version: Optional[str],
    model_id: Optional[str],
    model_version: Optional[str],
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
    ])


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _lock_age_seconds(doc: dict, now: datetime) -> float:
    ref = _parse_iso(doc.get("last_heartbeat_at")) or _parse_iso(doc.get("claimed_at"))
    if ref is None:
        return float("inf")
    return max(0.0, (now - ref).total_seconds())


def _is_lock_fresh(doc: dict, now: datetime) -> bool:
    return _lock_age_seconds(doc, now) < HEARTBEAT_FRESH_SECONDS


def _is_lock_stale(doc: dict, now: datetime) -> bool:
    return _lock_age_seconds(doc, now) >= STALE_LOCK_SECONDS


async def _ensure_indexes() -> None:
    global _index_ready
    if _index_ready:
        return
    db = get_database()
    col = db.concept_drift_job_locks
    await col.create_index("task_id", unique=True)
    await col.update_many(
        {"$or": [{"job_key": {"$exists": False}}, {"job_key": None}]},
        [{"$set": {"job_key": {"$concat": ["legacy:", "$task_id"]}}}],
    )
    try:
        await col.create_index(
            "job_key",
            unique=True,
            partialFilterExpression={"job_key": {"$exists": True, "$type": "string"}},
        )
    except Exception as e:
        logger.warning("job_key index create failed (%s); attempting drop+recreate", e)
        for index in await col.list_indexes().to_list(length=None):
            if index.get("name") != "_id_" and "job_key" in index.get("key", {}):
                await col.drop_index(index["name"])
        await col.create_index(
            "job_key",
            unique=True,
            partialFilterExpression={"job_key": {"$exists": True, "$type": "string"}},
        )
    _index_ready = True


class ConceptDriftJobClaimRequest(BaseModel):
    task_id: str = Field(..., description="Kafka task_id (idempotency key)")
    job_key: Optional[str] = Field(
        None,
        description="Stable dedup key: user|dataset|version|model|version",
    )
    user_id: str
    dataset_id: str
    dataset_version: Optional[str] = None
    model_id: Optional[str] = None
    model_version: Optional[str] = None


class ConceptDriftJobClaimResponse(BaseModel):
    task_id: str
    job_key: str
    claimed: bool
    claimed_at: str
    reclaimed: bool = False


class ConceptDriftJobTaskRequest(BaseModel):
    task_id: str


@router.post("/claim", response_model=ConceptDriftJobClaimResponse)
async def claim_concept_drift_job(payload: ConceptDriftJobClaimRequest) -> ConceptDriftJobClaimResponse:
    """
    Idempotency guard for concept-drift triggers.

    Stale in_progress locks can be reclaimed so redelivered Kafka messages are not
    stuck on "already claimed".
    """
    await _ensure_indexes()
    col = get_database().concept_drift_job_locks
    now_dt = datetime.now(tz=timezone.utc)
    now = now_dt.isoformat()
    resolved_job_key = build_concept_drift_job_key(
        user_id=payload.user_id,
        dataset_id=payload.dataset_id,
        dataset_version=payload.dataset_version,
        model_id=payload.model_id,
        model_version=payload.model_version,
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
        "status": "in_progress",
        "claimed_at": now,
        "last_heartbeat_at": now,
    }
    try:
        await col.insert_one(doc)
        return ConceptDriftJobClaimResponse(
            task_id=payload.task_id,
            job_key=resolved_job_key,
            claimed=True,
            claimed_at=now,
            reclaimed=False,
        )
    except DuplicateKeyError:
        existing = await col.find_one(
            {"$or": [{"task_id": payload.task_id}, {"job_key": resolved_job_key}]},
        )
        if not existing:
            raise HTTPException(status_code=409, detail="task_id or job_key already claimed")

        if existing.get("status") == "completed":
            raise HTTPException(status_code=409, detail="task_id already completed")

        fresh = _is_lock_fresh(existing, now_dt)
        stale = _is_lock_stale(existing, now_dt)

        if existing.get("task_id") == payload.task_id:
            if fresh:
                raise HTTPException(status_code=409, detail="task_id in progress")
            await col.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "status": "in_progress",
                    "last_heartbeat_at": now,
                    "claimed_at": now,
                }},
            )
            logger.warning(
                "Reclaimed stale task_id lock: task_id=%s age=%.0fs",
                payload.task_id,
                _lock_age_seconds(existing, now_dt),
            )
            return ConceptDriftJobClaimResponse(
                task_id=payload.task_id,
                job_key=resolved_job_key,
                claimed=True,
                claimed_at=now,
                reclaimed=True,
            )

        if existing.get("job_key") == resolved_job_key:
            if fresh or not stale:
                raise HTTPException(status_code=409, detail="job_key already claimed")
            await col.delete_one({"_id": existing["_id"]})
            try:
                await col.insert_one(doc)
            except DuplicateKeyError:
                raise HTTPException(status_code=409, detail="job_key already claimed")
            logger.warning(
                "Reclaimed stale job_key lock: job_key=%s old_task_id=%s new_task_id=%s",
                resolved_job_key,
                existing.get("task_id"),
                payload.task_id,
            )
            return ConceptDriftJobClaimResponse(
                task_id=payload.task_id,
                job_key=resolved_job_key,
                claimed=True,
                claimed_at=now,
                reclaimed=True,
            )

        raise HTTPException(status_code=409, detail="task_id or job_key already claimed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to claim concept drift job: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to claim concept drift job: {type(e).__name__}: {e}",
        )


@router.post("/heartbeat")
async def heartbeat_concept_drift_job(payload: ConceptDriftJobTaskRequest) -> dict:
    """Extend an in_progress lock while a long concept-drift job runs."""
    await _ensure_indexes()
    col = get_database().concept_drift_job_locks
    now = datetime.now(tz=timezone.utc).isoformat()
    result = await col.update_one(
        {"task_id": payload.task_id, "status": "in_progress"},
        {"$set": {"last_heartbeat_at": now}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="lock not found or not in progress")
    return {"task_id": payload.task_id, "last_heartbeat_at": now}


@router.post("/release")
async def release_concept_drift_job(payload: ConceptDriftJobTaskRequest) -> dict:
    """Release a lock after success/failure so retries and re-runs can claim again."""
    await _ensure_indexes()
    col = get_database().concept_drift_job_locks
    result = await col.delete_one({"task_id": payload.task_id})
    return {"task_id": payload.task_id, "released": result.deleted_count > 0}
