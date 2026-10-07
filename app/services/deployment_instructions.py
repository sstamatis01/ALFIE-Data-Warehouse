"""
Deployment instructions for AutoML models stored in AutoDW.

Primary source: ``*_deployment_instructions.md`` inside the model ZIP/folder
(already produced by the AutoML engine). Cached on the model Mongo document at
upload time so Agentic Core can fetch text without calling the AutoML host.

Fallback order on GET:
  1. Mongo ``deployment_instructions`` field
  2. Matching ``.md`` file already in MinIO for that model version
  3. Bundled static defaults under ``static_docs/deployment/`` (by modality)
"""
from __future__ import annotations

import logging
import os
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

INSTRUCTION_BASENAMES = (
    "tabular_deployment_instructions.md",
    "vision_deployment_instructions.md",
)


def _default_static_dir() -> Path:
    image_path = Path("/app/static_docs/deployment")
    if image_path.is_dir():
        return image_path
    return Path(__file__).resolve().parents[2] / "static_docs" / "deployment"


def is_deployment_instructions_filename(filename: str) -> bool:
    base = os.path.basename(filename or "").lower()
    if base in INSTRUCTION_BASENAMES:
        return True
    return base.endswith("deployment_instructions.md")


def modality_from_filename(filename: str) -> Optional[str]:
    base = os.path.basename(filename or "").lower()
    if base.startswith("tabular_"):
        return "tabular"
    if base.startswith("vision_"):
        return "vision"
    return None


def modality_from_model_type(model_type: Any) -> Optional[str]:
    raw = getattr(model_type, "value", model_type)
    s = str(raw or "").strip().lower()
    if s.startswith("tabular_") or s in {"regression", "time_series", "timeseries"}:
        return "tabular"
    # Bare "classification" is ambiguous (tabular vs vision); leave unset so caller can fall back.
    vision_prefixes = (
        "image_",
        "object_detection",
        "video_",
        "keypoint_",
        "audio_",
        "computer_vision",
    )
    if any(s.startswith(p) or s == p.rstrip("_") for p in vision_prefixes):
        return "vision"
    return None


def extract_from_text_file(filename: str, content: bytes) -> Optional[Dict[str, str]]:
    if not is_deployment_instructions_filename(filename):
        return None
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("utf-8", errors="replace")
    text = text.strip()
    if not text:
        return None
    return {
        "instructions": text,
        "filename": os.path.basename(filename),
        "modality": modality_from_filename(filename) or "unknown",
        "source": "upload",
    }


def extract_from_zip_bytes(zip_bytes: bytes) -> Optional[Dict[str, str]]:
    """Return the first deployment-instructions markdown found in a ZIP."""
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes), "r") as zf:
            # Prefer known names; then any *deployment_instructions.md
            names = [n for n in zf.namelist() if not n.endswith("/") and not n.startswith("__")]
            ordered: List[str] = []
            for wanted in INSTRUCTION_BASENAMES:
                ordered.extend(n for n in names if os.path.basename(n).lower() == wanted)
            ordered.extend(
                n
                for n in names
                if is_deployment_instructions_filename(n) and n not in ordered
            )
            for name in ordered:
                try:
                    data = zf.read(name)
                except Exception:
                    continue
                found = extract_from_text_file(name, data)
                if found:
                    found["source"] = "zip"
                    return found
    except zipfile.BadZipFile:
        return None
    except Exception as e:
        logger.warning("Could not scan ZIP for deployment instructions: %s", e)
    return None


def extract_from_model_files(
    files: List[Any],
    *,
    read_bytes,
) -> Optional[Dict[str, str]]:
    """
    Find instructions among already-uploaded ModelFile entries.

    ``read_bytes`` is a callable ``(file_path: str) -> bytes`` (sync or result of await).
    """
    candidates = []
    for f in files or []:
        filename = getattr(f, "filename", None) or (f.get("filename") if isinstance(f, dict) else None)
        file_path = getattr(f, "file_path", None) or (f.get("file_path") if isinstance(f, dict) else None)
        if filename and file_path and is_deployment_instructions_filename(filename):
            candidates.append((filename, file_path))
    # Prefer tabular_/vision_ canonical names
    def sort_key(item: Tuple[str, str]) -> int:
        base = os.path.basename(item[0]).lower()
        try:
            return INSTRUCTION_BASENAMES.index(base)
        except ValueError:
            return 99

    for filename, file_path in sorted(candidates, key=sort_key):
        try:
            data = read_bytes(file_path)
            found = extract_from_text_file(filename, data)
            if found:
                found["source"] = "minio"
                return found
        except Exception as e:
            logger.warning("Failed reading %s for deployment instructions: %s", file_path, e)
    return None


def bundled_fallback(modality: Optional[str]) -> Optional[Dict[str, str]]:
    if modality not in ("tabular", "vision"):
        return None
    path = _default_static_dir() / f"{modality}_deployment_instructions.md"
    if not path.is_file():
        logger.warning("Bundled deployment instructions missing: %s", path)
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    return {
        "instructions": text,
        "filename": path.name,
        "modality": modality,
        "source": "bundled",
    }
