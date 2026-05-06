from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional, Literal

from pydantic import BaseModel, Field


UploadJobStatus = Literal["queued", "running", "completed", "failed"]


class UploadJobProgress(BaseModel):
    phase: str = Field(default="queued", description="Current phase (e.g. upload_zip, extract, upload_v1, split_v2, finalize)")
    total_files: Optional[int] = Field(default=None, description="Total files expected to process (when known)")
    processed_files: int = Field(default=0, description="Number of files processed in current phase")
    message: Optional[str] = Field(default=None, description="Human-readable progress message")


class UploadJobResult(BaseModel):
    dataset_id: str
    v1: str
    v2: Optional[str] = None
    result_version: str


class UploadJobResponse(BaseModel):
    job_id: str
    status: UploadJobStatus
    user_id: str
    dataset_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    progress: UploadJobProgress
    result: Optional[UploadJobResult] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def now() -> datetime:
        return datetime.now(tz=timezone.utc)

