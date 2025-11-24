from fastapi import APIRouter, HTTPException, Header, Query
from typing import Optional
import logging
from ..models.bias_report import BiasReportCreate, BiasReportResponse
from ..services.bias_report_service import bias_report_service
from ..services.kafka_service import kafka_producer_service
from ..services.transformation_report_service import transformation_report_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bias-reports", tags=["bias-reports"])


@router.post("/", response_model=BiasReportResponse)
async def create_or_update_bias_report(
    payload: BiasReportCreate,
    task_id: Optional[str] = Header(None, alias="X-Task-ID")
):
    try:
        report = await bias_report_service.upsert_report(payload)
        
        # Send completion event if task_id is provided
        if task_id:
            try:
                await kafka_producer_service.send_bias_complete_event(
                    task_id=task_id,
                    dataset_id=payload.dataset_id,
                    dataset_version=payload.dataset_version,
                    user_id=payload.user_id,
                    bias_report_id=report.id,
                    success=True
                )
                logger.info(f"Bias completion event sent for task_id={task_id}")
            except Exception as e:
                logger.error(f"Failed to send bias completion event: {e}", exc_info=True)
        
        return report
    except ValueError as e:
        # Send failure event if task_id is provided
        if task_id:
            try:
                await kafka_producer_service.send_bias_complete_event(
                    task_id=task_id,
                    dataset_id=payload.dataset_id,
                    user_id=payload.user_id,
                    bias_report_id="",
                    success=False,
                    error_message=str(e)
                )
                logger.info(f"Bias failure event sent for task_id={task_id}")
            except Exception as kafka_error:
                logger.error(f"Failed to send bias failure event: {kafka_error}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Send failure event if task_id is provided
        if task_id:
            try:
                await kafka_producer_service.send_bias_complete_event(
                    task_id=task_id,
                    dataset_id=payload.dataset_id,
                    user_id=payload.user_id,
                    bias_report_id="",
                    success=False,
                    error_message="Failed to save bias report"
                )
                logger.info(f"Bias failure event sent for task_id={task_id}")
            except Exception as kafka_error:
                logger.error(f"Failed to send bias failure event: {kafka_error}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save bias report")


@router.get("/{user_id}/{dataset_id}", response_model=BiasReportResponse)
async def get_bias_report(
    user_id: str, 
    dataset_id: str,
    version: Optional[str] = Query(None, description="Dataset version (defaults to latest)")
):
    """Get bias report for a dataset (specific version or latest)"""
    report = await bias_report_service.get_report(user_id, dataset_id, version)
    if not report:
        version_msg = f" version {version}" if version else ""
        raise HTTPException(status_code=404, detail=f"Bias report not found for dataset {dataset_id}{version_msg}")
    return report


@router.get("/{user_id}/{dataset_id}/all", response_model=list[BiasReportResponse])
async def get_all_bias_reports(user_id: str, dataset_id: str):
    """Get all bias reports for a dataset (all versions)"""
    reports = await bias_report_service.get_all_reports(user_id, dataset_id)
    return reports


@router.delete("/{user_id}/{dataset_id}")
async def delete_bias_report(
    user_id: str, 
    dataset_id: str,
    version: Optional[str] = Query(None, description="Dataset version (deletes all versions if not specified)")
):
    """Delete bias report(s) for a dataset"""
    deleted = await bias_report_service.delete_report(user_id, dataset_id, version)
    if not deleted:
        version_msg = f" version {version}" if version else "s"
        raise HTTPException(status_code=404, detail=f"Bias report{version_msg} not found")
    
    version_msg = f" for version {version}" if version else "s"
    return {"message": f"Bias report{version_msg} deleted successfully"}
