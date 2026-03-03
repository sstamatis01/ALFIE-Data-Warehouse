from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from bson import ObjectId


class BiasReport(BaseModel):
    user_id: str = Field(..., description="User ID who owns the dataset")
    dataset_id: str = Field(..., description="Dataset ID the report relates to")
    dataset_version: str = Field(..., description="Dataset version used for bias detection")
    report: Any = Field(..., description="Arbitrary bias report structure (JSON-serializable)")
    transformation_report_id: Optional[str] = Field(None, description="ID of the transformation report if mitigation was performed")
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class BiasReportCreate(BaseModel):
    user_id: str
    dataset_id: str
    dataset_version: str
    report: Any
    target_column_name: Optional[str] = None
    task_type: Optional[str] = None
    is_folder: Optional[bool] = False
    file_count: Optional[int] = 1
    transformation_report_id: Optional[str] = None


class BiasReportResponse(BaseModel):
    id: Optional[str] = Field(None, description="Bias report document ID as string")
    user_id: str
    dataset_id: str
    dataset_version: str
    report: Any
    transformation_report_id: Optional[str] = Field(None, description="ID of the transformation report if mitigation was performed")
    created_at: datetime
    updated_at: datetime
