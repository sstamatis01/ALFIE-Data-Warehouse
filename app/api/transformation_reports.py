from fastapi import APIRouter, HTTPException
import logging
from ..models.transformation_report import TransformationReportCreate, TransformationReportResponse
from ..services.transformation_report_service import transformation_report_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transformation-reports", tags=["transformation-reports"])


@router.post("/", response_model=TransformationReportResponse)
async def create_or_update_transformation_report(payload: TransformationReportCreate):
    try:
        report = await transformation_report_service.upsert_report(payload)
        return report
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save transformation report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to save transformation report: {str(e)}")


@router.get("/{user_id}/{dataset_id}/{version}", response_model=TransformationReportResponse)
async def get_transformation_report(user_id: str, dataset_id: str, version: str):
    report = await transformation_report_service.get_report(user_id, dataset_id, version)
    if not report:
        raise HTTPException(status_code=404, detail="Transformation report not found")
    return report


@router.delete("/{user_id}/{dataset_id}/{version}")
async def delete_transformation_report(user_id: str, dataset_id: str, version: str):
    """Delete a transformation report"""
    deleted = await transformation_report_service.delete_report(user_id, dataset_id, version)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transformation report not found")
    return {"message": "Transformation report deleted successfully"}
