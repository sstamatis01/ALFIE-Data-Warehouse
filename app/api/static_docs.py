"""
Bundled static project documents (PDFs baked into the Docker image).

Served from the filesystem under STATIC_DOCS_DIR (default: /app/static_docs
in containers, or repo-root static_docs/ when running locally).
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/static-docs", tags=["static-docs"])


class StaticDocInfo(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    filename: str
    content_type: str = "application/pdf"
    size_bytes: Optional[int] = None
    download_url: str = Field(..., description="Relative download path for this API")


def _default_static_docs_dir() -> Path:
    """Prefer /app/static_docs in image; fall back to repo-root static_docs for local runs."""
    configured = getattr(settings, "static_docs_dir", None)
    if configured:
        return Path(configured)
    image_path = Path("/app/static_docs")
    if image_path.is_dir():
        return image_path
    # app/api/static_docs.py → repo root is parents[2]
    return Path(__file__).resolve().parents[2] / "static_docs"


@lru_cache(maxsize=1)
def _load_manifest() -> List[Dict[str, Any]]:
    docs_dir = _default_static_docs_dir()
    manifest_path = docs_dir / "manifest.json"
    if not manifest_path.is_file():
        logger.warning("static_docs manifest missing at %s", manifest_path)
        return []
    with manifest_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("documents") or [])


def _doc_by_id(doc_id: str) -> Dict[str, Any]:
    for doc in _load_manifest():
        if doc.get("id") == doc_id:
            return doc
    raise HTTPException(status_code=404, detail=f"Static document not found: {doc_id}")


def _file_path_for(doc: Dict[str, Any]) -> Path:
    docs_dir = _default_static_docs_dir()
    filename = doc.get("filename")
    if not filename:
        raise HTTPException(status_code=500, detail="Document filename missing in manifest")
    path = (docs_dir / filename).resolve()
    # Prevent path traversal outside the docs directory
    if not str(path).startswith(str(docs_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid document path")
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Document file missing on disk: {filename}",
        )
    return path


def _to_info(doc: Dict[str, Any], *, request: Optional[Request] = None) -> StaticDocInfo:
    path = _file_path_for(doc)
    doc_id = doc["id"]
    download_path = f"/static-docs/{doc_id}/download"
    # Prefer path-only URLs so clients can prefix with their API_BASE / ROOT_PATH
    return StaticDocInfo(
        id=doc_id,
        title=doc.get("title") or doc_id,
        description=doc.get("description"),
        filename=doc["filename"],
        content_type=doc.get("content_type") or "application/pdf",
        size_bytes=path.stat().st_size,
        download_url=download_path,
    )


@router.get("", response_model=List[StaticDocInfo])
@router.get("/", response_model=List[StaticDocInfo], include_in_schema=False)
async def list_static_docs(request: Request):
    """List bundled project documents available for download."""
    results: List[StaticDocInfo] = []
    for doc in _load_manifest():
        try:
            results.append(_to_info(doc, request=request))
        except HTTPException as e:
            if e.status_code == 404:
                logger.warning("Skipping missing static doc %s: %s", doc.get("id"), e.detail)
                continue
            raise
    return results


@router.get("/{doc_id}", response_model=StaticDocInfo)
async def get_static_doc(doc_id: str, request: Request):
    """Get metadata for a single bundled document."""
    return _to_info(_doc_by_id(doc_id), request=request)


@router.get("/{doc_id}/download")
async def download_static_doc(doc_id: str):
    """Download a bundled PDF (Content-Disposition: attachment)."""
    doc = _doc_by_id(doc_id)
    path = _file_path_for(doc)
    return FileResponse(
        path=path,
        media_type=doc.get("content_type") or "application/pdf",
        filename=doc.get("filename") or path.name,
        content_disposition_type="attachment",
    )
