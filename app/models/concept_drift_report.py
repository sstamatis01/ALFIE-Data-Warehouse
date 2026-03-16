from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field


class ConceptDriftReportCreate(BaseModel):
    """Payload for creating or updating a concept drift report (JSON)."""
    user_id: str = Field(..., description="User ID who owns the dataset/model")
    dataset_id: str = Field(..., description="Dataset ID the drift detection was run on")
    dataset_version: str = Field(..., description="Dataset version")
    model_id: str = Field(..., description="Model ID that was monitored for drift")
    model_version: str = Field(..., description="Model version (e.g. before or after retrain)")
    report: Any = Field(..., description="Concept drift report payload (JSON-serializable, e.g. drift_metrics, message)")


class ConceptDriftReportResponse(BaseModel):
    """Concept drift report as returned by the API."""
    id: Optional[str] = Field(None, description="Report document ID as string")
    user_id: str
    dataset_id: str
    dataset_version: str
    model_id: str
    model_version: str
    report: Any
    created_at: datetime
    updated_at: datetime
