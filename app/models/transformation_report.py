from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field


class TransformationReport(BaseModel):
    user_id: str = Field(...)
    dataset_id: str = Field(...)
    version: str = Field(..., description="Target version (e.g., v2) for mitigated dataset")
    report: Any = Field(..., description="Arbitrary transformation report structure")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class TransformationReportCreate(BaseModel):
    user_id: str
    dataset_id: str
    version: str
    report: Any


class TransformationReportResponse(BaseModel):
    id: Optional[str] = Field(None, description="Transformation report document ID as string")
    user_id: str
    dataset_id: str
    version: str
    report: Any
    created_at: datetime
    updated_at: datetime

