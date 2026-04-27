import os
import logging
from fastapi import APIRouter, Header, HTTPException

from ..services.gdpr_service import gdpr_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gdpr", tags=["gdpr"])


@router.delete("/users/{user_id}")
async def delete_user_everything(
    user_id: str,
    gdpr_token: str | None = Header(None, alias="X-GDPR-Token"),
):
    """
    GDPR / right-to-be-forgotten endpoint.

    Deletes all data for a given user_id from:
    - MinIO objects under known per-user prefixes
    - MongoDB documents in known collections (datasets, models, reports, user_files, users)
    - (Optional) Keycloak user (if KEYCLOAK_* env vars are provided and user_id is the Keycloak UUID)

    Safety:
    - Requires X-GDPR-Token matching env GDPR_DELETE_TOKEN (if set).
    """
    expected = os.getenv("GDPR_DELETE_TOKEN")
    if expected:
        if not gdpr_token or gdpr_token != expected:
            raise HTTPException(status_code=401, detail="Missing or invalid GDPR token")

    try:
        result = await gdpr_service.delete_user_everything(user_id)
        logger.info("GDPR delete completed for user_id=%s", user_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("GDPR delete failed for user_id=%s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Failed to delete user data")

