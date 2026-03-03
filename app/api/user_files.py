"""API endpoints for user-uploaded files (chatbot attachments)."""
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Path, Query, UploadFile
from fastapi.responses import Response

from ..models.user_file import UserFileListResponse, UserFileResponse
from ..services.user_file_service import user_file_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user-files", tags=["user-files"])


@router.post("/upload/{user_id}", response_model=UserFileResponse)
async def upload_user_file(
    user_id: str = Path(..., description="User ID"),
    file: UploadFile = File(..., description="File to upload"),
    name: Optional[str] = Form(None, description="Display name"),
    description: Optional[str] = Form(None, description="Description"),
    project_id: Optional[str] = Form(None, description="Project/conversation ID"),
):
    """Upload a file. Body: multipart form with file (required), optional name, description, project_id."""
    try:
        return await user_file_service.upload_file(
            user_id=user_id,
            file=file,
            name=name,
            description=description,
            project_id=project_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")


@router.get("/{user_id}", response_model=UserFileListResponse)
async def list_user_files(
    user_id: str = Path(..., description="User ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """List files for a user. Query: project_id, skip, limit."""
    try:
        files, total = await user_file_service.list_files(
            user_id=user_id,
            project_id=project_id,
            skip=skip,
            limit=limit,
        )
        return UserFileListResponse(files=files, total=total)
    except Exception as e:
        logger.error(f"List files error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")


@router.get("/{user_id}/{file_id}/download")
async def download_user_file(
    user_id: str = Path(..., description="User ID"),
    file_id: str = Path(..., description="File ID"),
):
    """Download file (for other services: parse, summarize, etc.)."""
    try:
        data, content_type, filename = await user_file_service.download_file(
            user_id=user_id,
            file_id=file_id,
        )
    except HTTPException:
        raise
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{user_id}/{file_id}", response_model=UserFileResponse)
async def get_user_file_metadata(
    user_id: str = Path(..., description="User ID"),
    file_id: str = Path(..., description="File ID"),
):
    """Get metadata for one file."""
    meta = await user_file_service.get_file(user_id=user_id, file_id=file_id)
    if not meta:
        raise HTTPException(status_code=404, detail="File not found")
    return meta


@router.delete("/{user_id}/{file_id}")
async def delete_user_file(
    user_id: str = Path(..., description="User ID"),
    file_id: str = Path(..., description="File ID"),
):
    """Delete file (from UI or API)."""
    deleted = await user_file_service.delete_file(user_id=user_id, file_id=file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    return {"message": "File deleted", "file_id": file_id}
