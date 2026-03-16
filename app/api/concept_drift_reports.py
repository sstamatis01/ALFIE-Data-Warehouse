from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional, List
import logging

from ..models.concept_drift_report import ConceptDriftReportCreate, ConceptDriftReportResponse
from ..services.concept_drift_report_service import concept_drift_report_service
from ..services.kafka_service import kafka_producer_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/concept-drift-reports", tags=["concept-drift-reports"])


@router.post("/", response_model=ConceptDriftReportResponse)
async def create_or_update_concept_drift_report(
    payload: ConceptDriftReportCreate,
    task_id: Optional[str] = Header(None, alias="X-Task-ID"),
):
    """
    Create or update a concept drift report (JSON).
    Unique per (user_id, dataset_id, dataset_version, model_id, model_version).
    Send X-Task-ID to emit a concept-drift-complete Kafka event on success/failure.
    """
    try:
        report = await concept_drift_report_service.upsert_report(payload)
        if task_id:
            try:
                await kafka_producer_service.send_concept_drift_complete_event(
                    task_id=task_id,
                    user_id=payload.user_id,
                    dataset_id=payload.dataset_id,
                    dataset_version=payload.dataset_version,
                    model_id=payload.model_id,
                    model_version=payload.model_version,
                    success=True,
                    drift_metrics=payload.report if isinstance(payload.report, dict) else None,
                )
                logger.info(f"Concept drift completion event sent for task_id={task_id}")
            except Exception as e:
                logger.error(f"Failed to send concept drift completion event: {e}", exc_info=True)
        return report
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save concept drift report: {e}", exc_info=True)
        if task_id:
            try:
                await kafka_producer_service.send_concept_drift_complete_event(
                    task_id=task_id,
                    user_id=payload.user_id,
                    dataset_id=payload.dataset_id,
                    dataset_version=payload.dataset_version,
                    model_id=payload.model_id,
                    model_version=payload.model_version,
                    success=False,
                    error_message="Failed to save concept drift report",
                )
            except Exception as kafka_error:
                logger.error(f"Failed to send concept drift failure event: {kafka_error}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save concept drift report: {str(e)}")


@router.get("/{user_id}/{dataset_id}/{model_id}", response_model=ConceptDriftReportResponse)
async def get_concept_drift_report(
    user_id: str,
    dataset_id: str,
    model_id: str,
    dataset_version: Optional[str] = Query(None, description="Dataset version (defaults to latest)"),
    model_version: Optional[str] = Query(None, description="Model version (defaults to latest)"),
):
    """Get concept drift report for a dataset/model (specific versions or latest)."""
    report = await concept_drift_report_service.get_report(
        user_id, dataset_id, model_id, dataset_version, model_version
    )
    if not report:
        version_msg = ""
        if dataset_version or model_version:
            version_msg = f" for dataset_version={dataset_version or 'latest'}, model_version={model_version or 'latest'}"
        raise HTTPException(
            status_code=404,
            detail=f"Concept drift report not found for dataset {dataset_id}, model {model_id}{version_msg}",
        )
    return report


@router.get("/{user_id}/{dataset_id}/{model_id}/all", response_model=List[ConceptDriftReportResponse])
async def get_all_concept_drift_reports(
    user_id: str,
    dataset_id: str,
    model_id: str,
    dataset_version: Optional[str] = Query(None, description="Filter by dataset version"),
    model_version: Optional[str] = Query(None, description="Filter by model version"),
):
    """Get all concept drift reports for a dataset/model (optionally filtered by versions)."""
    return await concept_drift_report_service.get_all_reports(
        user_id, dataset_id, model_id, dataset_version, model_version
    )


@router.delete("/{user_id}/{dataset_id}/{model_id}")
async def delete_concept_drift_report(
    user_id: str,
    dataset_id: str,
    model_id: str,
    dataset_version: Optional[str] = Query(None, description="Dataset version (omit to delete all versions)"),
    model_version: Optional[str] = Query(None, description="Model version (omit to delete all versions)"),
):
    """Delete concept drift report(s). Omit version params to delete all reports for this dataset/model."""
    deleted = await concept_drift_report_service.delete_report(
        user_id, dataset_id, model_id, dataset_version, model_version
    )
    if not deleted:
        if dataset_version or model_version:
            detail = f"Concept drift report for dataset_version={dataset_version}, model_version={model_version} not found"
        else:
            detail = "No concept drift reports found for this dataset/model"
        raise HTTPException(status_code=404, detail=detail)
    if dataset_version or model_version:
        return {"message": "Concept drift report deleted successfully"}
    return {"message": "Concept drift reports deleted successfully"}
