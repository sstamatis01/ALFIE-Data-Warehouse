<<<<<<< HEAD
from datetime import datetime, timezone
=======
from datetime import datetime
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from bson import ObjectId


class BiasReport(BaseModel):
    user_id: str = Field(..., description="User ID who owns the dataset")
    dataset_id: str = Field(..., description="Dataset ID the report relates to")
    report: Any = Field(..., description="Arbitrary bias report structure (JSON-serializable)")
<<<<<<< HEAD
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
=======
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96


class BiasReportCreate(BaseModel):
    user_id: str
    dataset_id: str
    report: Any
    target_column_name: Optional[str] = None
    task_type: Optional[str] = None
    is_folder: Optional[bool] = False
    file_count: Optional[int] = 1


class BiasReportResponse(BaseModel):
    id: Optional[str] = Field(None, description="Bias report document ID as string")
    user_id: str
    dataset_id: str
    report: Any
    created_at: datetime
    updated_at: datetime
