"""Service for user-uploaded files (chatbot attachments) stored in MinIO + MongoDB."""
import re
import logging
from io import BytesIO
from typing import Optional
from datetime import datetime, timezone

from fastapi import UploadFile, HTTPException
from bson import ObjectId

from ..core.database import get_database
from ..core.minio_client import minio_client
from ..models.user_file import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE_BYTES,
    UserFile,
    UserFileResponse,
)

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Keep only safe characters for object name; avoid path traversal."""
    name = name.replace("\\", "/").lstrip("/")
    name = re.sub(r"[^\w\s\-\.]", "", name).strip() or "file"
    return name[:200]


def _get_extension(filename: str) -> str:
    """Return lower-case extension including dot, or empty string."""
    if "." in filename:
        return "." + filename.rsplit(".", 1)[-1].lower()
    return ""


class UserFileService:
    def __init__(self):
        self.client = None
        self.bucket_name = minio_client.bucket_name
        self.db = None
        self.collection = None

    async def initialize(self):
        await minio_client.connect()
        self.client = minio_client.get_client()
        self.db = get_database()
        self.collection = self.db.user_files

    def _to_response(self, doc: dict) -> UserFileResponse:
        return UserFileResponse(
            file_id=doc["file_id"],
            user_id=doc["user_id"],
            name=doc.get("name"),
            description=doc.get("description"),
            project_id=doc.get("project_id"),
            original_filename=doc["original_filename"],
            content_type=doc["content_type"],
            size_bytes=doc["size_bytes"],
            created_at=doc["created_at"],
        )

    async def upload_file(
        self,
        user_id: str,
        file: UploadFile,
        name: Optional[str] = None,
        description: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> UserFileResponse:
        """Upload a file to MinIO and save metadata in MongoDB. Returns metadata with file_id."""
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        ext = _get_extension(file.filename)
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
            )

        data = await file.read()
        size = len(data)
        if size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {MAX_FILE_SIZE_BYTES // (1024*1024)} MB",
            )

        file_id = str(ObjectId())
        safe_name = _sanitize_filename(file.filename)
        file_path = f"user-files/{user_id}/{file_id}/{safe_name}"

        content_type = file.content_type or "application/octet-stream"

        try:
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=file_path,
                data=BytesIO(data),
                length=size,
                content_type=content_type,
            )
        except Exception as e:
            logger.error(f"MinIO upload error: {e}")
            raise HTTPException(status_code=500, detail="Failed to store file")

        doc = {
            "file_id": file_id,
            "user_id": user_id,
            "name": name,
            "description": description,
            "project_id": project_id,
            "file_path": file_path,
            "original_filename": file.filename,
            "content_type": content_type,
            "size_bytes": size,
            "created_at": datetime.now(tz=timezone.utc),
        }
        await self.collection.insert_one(doc)
        logger.info(f"User file uploaded: {file_path}")
        return self._to_response(doc)

    async def list_files(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[UserFileResponse], int]:
        """List files for a user. Returns (items, total_count)."""
        query = {"user_id": user_id}
        if project_id is not None:
            query["project_id"] = project_id

        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [self._to_response(d) for d in docs], total

    async def get_file(self, user_id: str, file_id: str) -> Optional[UserFileResponse]:
        """Get metadata for one file. Returns None if not found or not owned by user."""
        doc = await self.collection.find_one({"user_id": user_id, "file_id": file_id})
        if not doc:
            return None
        return self._to_response(doc)

    async def get_file_doc(self, user_id: str, file_id: str) -> Optional[dict]:
        """Get raw document (includes file_path) for download/delete. None if not found."""
        return await self.collection.find_one({"user_id": user_id, "file_id": file_id})

    async def download_file(self, user_id: str, file_id: str) -> tuple[bytes, str, str]:
        """Download file bytes from MinIO. Returns (data, content_type, filename). Raises HTTPException if not found."""
        doc = await self.get_file_doc(user_id, file_id)
        if not doc:
            raise HTTPException(status_code=404, detail="File not found")

        try:
            response = self.client.get_object(self.bucket_name, doc["file_path"])
            data = response.read()
            return data, doc["content_type"], doc["original_filename"]
        except Exception as e:
            logger.error(f"MinIO download error: {e}")
            raise HTTPException(status_code=404, detail="File not found")

    async def delete_file(self, user_id: str, file_id: str) -> bool:
        """Delete file from MinIO and MongoDB. Returns True if deleted."""
        doc = await self.get_file_doc(user_id, file_id)
        if not doc:
            return False

        try:
            self.client.remove_object(self.bucket_name, doc["file_path"])
        except Exception as e:
            logger.warning(f"MinIO delete error: {e}")

        result = await self.collection.delete_one({"user_id": user_id, "file_id": file_id})
        if result.deleted_count:
            logger.info(f"User file deleted: {doc['file_path']}")
        return result.deleted_count > 0


user_file_service = UserFileService()
