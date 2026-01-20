<<<<<<< HEAD
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, Query
from fastapi.responses import HTMLResponse
from typing import List, Optional
import logging

from ..models.xai_report import (
    XAIReportCreate,
    XAIReportResponse,
    ReportType,
    ExpertiseLevel
)
from ..services.xai_report_service import xai_report_service
from ..services.kafka_service import kafka_producer_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/xai-reports", tags=["XAI Reports"])


@router.post("/upload/{user_id}", response_model=XAIReportResponse)
async def upload_xai_report(
    user_id: str,
    file: UploadFile = File(...),
    dataset_id: str = Form(...),
    dataset_version: str = Form(...),
    model_id: str = Form(...),
    model_version: str = Form(...),
    report_type: ReportType = Form(...),
    level: ExpertiseLevel = Form(...),
    task_id: Optional[str] = Header(None, alias="X-Task-ID")
):
    """
    Upload an XAI report HTML file
    
    - **user_id**: User ID (path parameter)
    - **file**: HTML file containing the XAI explanation
    - **dataset_id**: Dataset ID
    - **model_id**: AI Model ID
    - **report_type**: Type of report (model_explanation or data_explanation)
    - **level**: Expertise level (beginner or expert)
    """
    try:
        report_data = XAIReportCreate(
            user_id=user_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            model_id=model_id,
            model_version=model_version,
            report_type=report_type,
            level=level
        )

        result = await xai_report_service.upload_report(file, report_data)
        
        # Send Kafka XAI completion event if task_id is provided
        if task_id:
            try:
                await kafka_producer_service.send_xai_complete_event(
                    task_id=task_id,
                    user_id=user_id,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    model_id=model_id,
                    model_version=model_version,
                    xai_report_id=str(result.id) if hasattr(result, 'id') else str(result),
                    success=True
                )
                logger.info(f"XAI completion event sent for task_id={task_id}")
            except Exception as e:
                logger.error(f"Failed to send XAI completion event: {e}", exc_info=True)
        
        return result

    except HTTPException:
        raise
    except Exception as e:
        # Send failure event if task_id is provided
        if task_id:
            try:
                await kafka_producer_service.send_xai_complete_event(
                    task_id=task_id,
                    user_id=user_id,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    model_id=model_id,
                    model_version=model_version,
                    xai_report_id="",
                    success=False,
                    error_message="Failed to upload XAI report"
                )
                logger.info(f"XAI failure event sent for task_id={task_id}")
            except Exception as kafka_error:
                logger.error(f"Failed to send XAI failure event: {kafka_error}", exc_info=True)
        logger.error(f"Error uploading XAI report: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload XAI report")


@router.get("/{user_id}/{dataset_id}/{model_id}", response_model=List[XAIReportResponse])
async def get_all_xai_reports(
    user_id: str,
    dataset_id: str,
    model_id: str,
    dataset_version: Optional[str] = Query(None, description="Dataset version filter"),
    model_version: Optional[str] = Query(None, description="Model version filter")
):
    """
    Get all XAI reports for a specific model and dataset (optionally filtered by versions)
    """
    try:
        reports = await xai_report_service.get_all_reports(
            user_id, dataset_id, model_id, dataset_version, model_version
        )
        return reports
    except Exception as e:
        logger.error(f"Error retrieving XAI reports: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve XAI reports")


@router.get("/{user_id}/{dataset_id}/{model_id}/{report_type}/{level}", response_model=XAIReportResponse)
async def get_xai_report(
    user_id: str,
    dataset_id: str,
    model_id: str,
    report_type: ReportType,
    level: ExpertiseLevel,
    dataset_version: Optional[str] = Query(None, description="Dataset version (defaults to latest)"),
    model_version: Optional[str] = Query(None, description="Model version (defaults to latest)")
):
    """
    Get a specific XAI report metadata (specific versions or latest)
    """
    report = await xai_report_service.get_report(
        user_id, dataset_id, model_id, report_type, level, dataset_version, model_version
    )
    
    if not report:
        version_msg = ""
        if dataset_version or model_version:
            version_msg = f" for dataset v{dataset_version or 'latest'} and model v{model_version or 'latest'}"
        raise HTTPException(status_code=404, detail=f"XAI report not found{version_msg}")
    
    return report


@router.get("/{user_id}/{dataset_id}/{model_id}/{report_type}/{level}/view", response_class=HTMLResponse)
async def view_xai_report(
    user_id: str,
    dataset_id: str,
    model_id: str,
    report_type: ReportType,
    level: ExpertiseLevel,
    dataset_version: Optional[str] = Query(None, description="Dataset version (defaults to latest)"),
    model_version: Optional[str] = Query(None, description="Model version (defaults to latest)")
):
    """
    View the XAI report HTML content directly in browser (specific versions or latest)
    """
    # Get report metadata
    report = await xai_report_service.get_report(
        user_id, dataset_id, model_id, report_type, level, dataset_version, model_version
    )
    
    if not report:
        version_msg = ""
        if dataset_version or model_version:
            version_msg = f" for dataset v{dataset_version or 'latest'} and model v{model_version or 'latest'}"
        raise HTTPException(status_code=404, detail=f"XAI report not found{version_msg}")
    
    # Download HTML content
    html_content = await xai_report_service.download_report(report.file_path)
    
    return HTMLResponse(content=html_content.decode('utf-8'))


@router.delete("/{user_id}/{dataset_id}/{model_id}/{report_type}/{level}")
async def delete_xai_report(
    user_id: str,
    dataset_id: str,
    model_id: str,
    report_type: ReportType,
    level: ExpertiseLevel,
    dataset_version: Optional[str] = Query(None, description="Dataset version (deletes latest if not specified)"),
    model_version: Optional[str] = Query(None, description="Model version (deletes latest if not specified)")
):
    """
    Delete a specific XAI report (specific versions or latest)
    """
    deleted = await xai_report_service.delete_report(
        user_id, dataset_id, model_id, report_type, level, dataset_version, model_version
    )
    
    if not deleted:
        version_msg = ""
        if dataset_version or model_version:
            version_msg = f" for dataset v{dataset_version or 'latest'} and model v{model_version or 'latest'}"
        raise HTTPException(status_code=404, detail=f"XAI report not found{version_msg}")
    
    return {
        "message": "XAI report deleted successfully",
        "user_id": user_id,
        "dataset_id": dataset_id,
        "model_id": model_id,
        "report_type": report_type,
        "level": level,
        "dataset_version": dataset_version,
        "model_version": model_version
    }

=======
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, Query
from fastapi.responses import HTMLResponse
from typing import List, Optional
import logging

from ..models.xai_report import (
    XAIReportCreate,
    XAIReportResponse,
    ReportType,
    ExpertiseLevel
)
from ..services.xai_report_service import xai_report_service
from ..services.kafka_service import kafka_producer_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/xai-reports", tags=["XAI Reports"])


@router.post("/upload/{user_id}", response_model=XAIReportResponse)
async def upload_xai_report(
    user_id: str,
    file: UploadFile = File(...),
    dataset_id: str = Form(...),
    dataset_version: str = Form(...),
    model_id: str = Form(...),
    model_version: str = Form(...),
    report_type: ReportType = Form(...),
    level: ExpertiseLevel = Form(...),
    task_id: Optional[str] = Header(None, alias="X-Task-ID")
):
    """
    Upload an XAI report HTML file
    
    - **user_id**: User ID (path parameter)
    - **file**: HTML file containing the XAI explanation
    - **dataset_id**: Dataset ID
    - **model_id**: AI Model ID
    - **report_type**: Type of report (model_explanation or data_explanation)
    - **level**: Expertise level (beginner or expert)
    """
    try:
        report_data = XAIReportCreate(
            user_id=user_id,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            model_id=model_id,
            model_version=model_version,
            report_type=report_type,
            level=level
        )

        result = await xai_report_service.upload_report(file, report_data)
        
        # Send Kafka XAI completion event if task_id is provided
        if task_id:
            try:
                await kafka_producer_service.send_xai_complete_event(
                    task_id=task_id,
                    user_id=user_id,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    model_id=model_id,
                    model_version=model_version,
                    xai_report_id=str(result.id) if hasattr(result, 'id') else str(result),
                    success=True
                )
                logger.info(f"XAI completion event sent for task_id={task_id}")
            except Exception as e:
                logger.error(f"Failed to send XAI completion event: {e}", exc_info=True)
        
        return result

    except HTTPException:
        raise
    except Exception as e:
        # Send failure event if task_id is provided
        if task_id:
            try:
                await kafka_producer_service.send_xai_complete_event(
                    task_id=task_id,
                    user_id=user_id,
                    dataset_id=dataset_id,
                    dataset_version=dataset_version,
                    model_id=model_id,
                    model_version=model_version,
                    xai_report_id="",
                    success=False,
                    error_message="Failed to upload XAI report"
                )
                logger.info(f"XAI failure event sent for task_id={task_id}")
            except Exception as kafka_error:
                logger.error(f"Failed to send XAI failure event: {kafka_error}", exc_info=True)
        logger.error(f"Error uploading XAI report: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload XAI report")


@router.get("/{user_id}/{dataset_id}/{model_id}", response_model=List[XAIReportResponse])
async def get_all_xai_reports(
    user_id: str,
    dataset_id: str,
    model_id: str,
    dataset_version: Optional[str] = Query(None, description="Dataset version filter"),
    model_version: Optional[str] = Query(None, description="Model version filter")
):
    """
    Get all XAI reports for a specific model and dataset (optionally filtered by versions)
    """
    try:
        reports = await xai_report_service.get_all_reports(
            user_id, dataset_id, model_id, dataset_version, model_version
        )
        return reports
    except Exception as e:
        logger.error(f"Error retrieving XAI reports: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve XAI reports")


@router.get("/{user_id}/{dataset_id}/{model_id}/{report_type}/{level}", response_model=XAIReportResponse)
async def get_xai_report(
    user_id: str,
    dataset_id: str,
    model_id: str,
    report_type: ReportType,
    level: ExpertiseLevel,
    dataset_version: Optional[str] = Query(None, description="Dataset version (defaults to latest)"),
    model_version: Optional[str] = Query(None, description="Model version (defaults to latest)")
):
    """
    Get a specific XAI report metadata (specific versions or latest)
    """
    report = await xai_report_service.get_report(
        user_id, dataset_id, model_id, report_type, level, dataset_version, model_version
    )
    
    if not report:
        version_msg = ""
        if dataset_version or model_version:
            version_msg = f" for dataset v{dataset_version or 'latest'} and model v{model_version or 'latest'}"
        raise HTTPException(status_code=404, detail=f"XAI report not found{version_msg}")
    
    return report


@router.get("/{user_id}/{dataset_id}/{model_id}/{report_type}/{level}/view", response_class=HTMLResponse)
async def view_xai_report(
    user_id: str,
    dataset_id: str,
    model_id: str,
    report_type: ReportType,
    level: ExpertiseLevel,
    dataset_version: Optional[str] = Query(None, description="Dataset version (defaults to latest)"),
    model_version: Optional[str] = Query(None, description="Model version (defaults to latest)")
):
    """
    View the XAI report HTML content directly in browser (specific versions or latest)
    """
    # Get report metadata
    report = await xai_report_service.get_report(
        user_id, dataset_id, model_id, report_type, level, dataset_version, model_version
    )
    
    if not report:
        version_msg = ""
        if dataset_version or model_version:
            version_msg = f" for dataset v{dataset_version or 'latest'} and model v{model_version or 'latest'}"
        raise HTTPException(status_code=404, detail=f"XAI report not found{version_msg}")
    
    # Download HTML content
    html_content = await xai_report_service.download_report(report.file_path)
    
    return HTMLResponse(content=html_content.decode('utf-8'))


@router.delete("/{user_id}/{dataset_id}/{model_id}/{report_type}/{level}")
async def delete_xai_report(
    user_id: str,
    dataset_id: str,
    model_id: str,
    report_type: ReportType,
    level: ExpertiseLevel,
    dataset_version: Optional[str] = Query(None, description="Dataset version (deletes latest if not specified)"),
    model_version: Optional[str] = Query(None, description="Model version (deletes latest if not specified)")
):
    """
    Delete a specific XAI report (specific versions or latest)
    """
    deleted = await xai_report_service.delete_report(
        user_id, dataset_id, model_id, report_type, level, dataset_version, model_version
    )
    
    if not deleted:
        version_msg = ""
        if dataset_version or model_version:
            version_msg = f" for dataset v{dataset_version or 'latest'} and model v{model_version or 'latest'}"
        raise HTTPException(status_code=404, detail=f"XAI report not found{version_msg}")
    
    return {
        "message": "XAI report deleted successfully",
        "user_id": user_id,
        "dataset_id": dataset_id,
        "model_id": model_id,
        "report_type": report_type,
        "level": level,
        "dataset_version": dataset_version,
        "model_version": model_version
    }

>>>>>>> 9071a9c69b92669f03f3884d4a945a40b8296d96
