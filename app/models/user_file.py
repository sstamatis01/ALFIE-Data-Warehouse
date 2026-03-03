"""Models for user-uploaded files (chatbot attachments, etc.)."""
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from pydantic import BaseModel, Field


# Allowed extensions for user uploads (text/docs for chatbot)
ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml",
    ".pdf", ".doc", ".docx", ".odt", ".rtf",
}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


class UserFile(BaseModel):
    """MongoDB document for a user-uploaded file."""
    id: Optional[ObjectId] = Field(default_factory=ObjectId, alias="_id")
    file_id: str = Field(..., description="Unique file identifier (string representation of _id)")
    user_id: str = Field(..., description="Owner user id")
    name: Optional[str] = Field(None, description="Display name")
    description: Optional[str] = Field(None, description="Optional description")
    project_id: Optional[str] = Field(None, description="Optional project/conversation id")
    file_path: str = Field(..., description="Path in MinIO: user-files/{user_id}/{file_id}/...")
    original_filename: str = Field(..., description="Original filename as uploaded")
    content_type: str = Field(..., description="MIME type")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True


class UserFileResponse(BaseModel):
    """Response model for a single user file (metadata only)."""
    file_id: str
    user_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[str] = None
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class UserFileListResponse(BaseModel):
    """List response with total count."""
    files: list[UserFileResponse]
    total: int
