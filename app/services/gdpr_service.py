import os
import logging
from typing import Any, Dict

import requests
from fastapi import HTTPException

from ..core.database import get_database
from ..core.minio_client import minio_client

logger = logging.getLogger(__name__)


class GDPRService:
    """
    Delete all user data from:
    - MinIO objects under known user prefixes
    - MongoDB documents in known collections containing user_id
    - (Optional) Keycloak user (admin API), if env vars are provided
    """

    def __init__(self) -> None:
        self.client = None
        self.bucket_name = minio_client.bucket_name
        self.db = None

    async def initialize(self) -> None:
        await minio_client.connect()
        self.client = minio_client.get_client()
        self.db = get_database()

    def _delete_minio_prefix(self, prefix: str) -> int:
        deleted = 0
        objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
        for obj in objects:
            try:
                self.client.remove_object(self.bucket_name, obj.object_name)
                deleted += 1
            except Exception as e:
                logger.warning("Failed deleting MinIO object %s: %s", obj.object_name, e)
        return deleted

    async def _delete_mongo_user_docs(self, user_id: str) -> Dict[str, int]:
        """
        Delete user_id-scoped documents from all known collections.
        Returns per-collection deleted counts.
        """
        collections = [
            "datasets",
            "ai_models",
            "bias_reports",
            "transformation_reports",
            "concept_drift_reports",
            "xai_reports",
            "user_files",
            "users",
        ]
        out: Dict[str, int] = {}
        for name in collections:
            coll = getattr(self.db, name, None)
            if coll is None:
                out[name] = 0
                continue
            try:
                result = await coll.delete_many({"user_id": user_id})
                out[name] = int(result.deleted_count or 0)
            except Exception as e:
                logger.error("Mongo delete_many failed for %s user_id=%s: %s", name, user_id, e)
                raise HTTPException(status_code=500, detail=f"Failed to delete MongoDB data for collection '{name}'")
        return out

    def _keycloak_admin_token(self) -> str | None:
        """
        Get a Keycloak admin access token.
        Supports either:
        - client_credentials: KEYCLOAK_ADMIN_CLIENT_ID + KEYCLOAK_ADMIN_CLIENT_SECRET
        - password grant: KEYCLOAK_ADMIN_USERNAME + KEYCLOAK_ADMIN_PASSWORD + KEYCLOAK_ADMIN_CLIENT_ID
        """
        base = (os.getenv("KEYCLOAK_URL") or "").rstrip("/")
        realm = (os.getenv("KEYCLOAK_REALM") or "").strip()
        if not base or not realm:
            return None

        token_url = f"{base}/realms/{realm}/protocol/openid-connect/token"
        client_id = os.getenv("KEYCLOAK_ADMIN_CLIENT_ID") or ""
        client_secret = os.getenv("KEYCLOAK_ADMIN_CLIENT_SECRET")
        username = os.getenv("KEYCLOAK_ADMIN_USERNAME")
        password = os.getenv("KEYCLOAK_ADMIN_PASSWORD")

        if not client_id:
            return None

        data: Dict[str, Any]
        if client_secret:
            data = {
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }
        elif username and password:
            data = {
                "grant_type": "password",
                "client_id": client_id,
                "username": username,
                "password": password,
            }
        else:
            return None

        try:
            r = requests.post(token_url, data=data, timeout=15)
            r.raise_for_status()
            payload = r.json() if r.content else {}
            return payload.get("access_token")
        except Exception as e:
            logger.warning("Failed to obtain Keycloak admin token: %s", e)
            return None

    def _delete_keycloak_user(self, user_id: str) -> bool:
        """
        Attempt to delete the user in Keycloak by ID.
        Assumes DW user_id corresponds to the Keycloak user UUID (sub).
        Returns True if deleted, False if skipped/not configured/not found.
        """
        token = self._keycloak_admin_token()
        if not token:
            return False

        base = (os.getenv("KEYCLOAK_URL") or "").rstrip("/")
        realm = (os.getenv("KEYCLOAK_REALM") or "").strip()
        if not base or not realm:
            return False

        url = f"{base}/admin/realms/{realm}/users/{user_id}"
        try:
            r = requests.delete(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
            if r.status_code in (204, 200):
                return True
            if r.status_code == 404:
                return False
            logger.warning("Keycloak user delete failed status=%s body=%s", r.status_code, r.text[:300])
            return False
        except Exception as e:
            logger.warning("Keycloak user delete request failed: %s", e)
            return False

    async def delete_user_everything(self, user_id: str) -> Dict[str, Any]:
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id is required")

        # 1) MinIO deletes (best-effort; keep going)
        minio_prefixes = {
            "datasets": f"datasets/{user_id}/",
            "models": f"models/{user_id}/",
            "user_files": f"user-files/{user_id}/",
            "xai_reports": f"xai_reports/{user_id}/",
        }
        minio_deleted: Dict[str, int] = {}
        for k, prefix in minio_prefixes.items():
            try:
                minio_deleted[k] = self._delete_minio_prefix(prefix)
            except Exception as e:
                logger.warning("Failed deleting MinIO prefix %s (%s): %s", k, prefix, e)
                minio_deleted[k] = 0

        # 2) Mongo deletes (authoritative; if this fails, return 500)
        mongo_deleted = await self._delete_mongo_user_docs(user_id)

        # 3) Optional Keycloak delete
        keycloak_deleted = self._delete_keycloak_user(user_id)

        return {
            "user_id": user_id,
            "minio_deleted": minio_deleted,
            "mongo_deleted": mongo_deleted,
            "keycloak_user_deleted": keycloak_deleted,
        }


gdpr_service = GDPRService()

