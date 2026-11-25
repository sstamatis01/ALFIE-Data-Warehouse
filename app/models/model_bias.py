from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelBiasAuditRequest(BaseModel):
    """Run an Aequitas audit for a stored model on a stored dataset."""

    user_id: str
    model_id: str
    dataset_id: Optional[str] = Field(
        None,
        description="Dataset to score. Defaults to the model's training_dataset.",
    )
    dataset_version: Optional[str] = Field(
        None,
        description="Dataset version. Defaults to the latest bias report's version, else the latest dataset.",
    )
    model_version: Optional[str] = Field(
        None,
        description="Model version. Defaults to the latest model for this user and model_id.",
    )
    protected_attributes: Optional[List[str]] = Field(
        None,
        description="Override. When omitted, attributes are taken from the dataset bias report.",
    )
    positive_label: Optional[str] = Field(
        None,
        description="Class treated as 1. Defaults to the bias report pos_label when the label is not already 0/1.",
    )
    split: Optional[str] = Field(
        None,
        description="train, test, or drift. Defaults to test when the dataset has a split.",
    )
    score_threshold: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        description="Cutoff used when the model returns probabilities.",
    )


class ModelBiasAuditResponse(BaseModel):
    id: Optional[str] = None
    user_id: str
    model_id: str
    model_version: str
    dataset_id: str
    dataset_version: str
    protected_attributes: List[str]
    reference_groups: Dict[str, str]
    positive_label: Optional[str] = None
    label_mode: str
    eval_split: Optional[str] = None
    scorer: str
    n_rows: int
    report: Dict[str, Any]
    alerts: List[str] = Field(default_factory=list)
    notes: List[str]
    created_at: datetime
