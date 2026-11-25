"""Unpack stored model archives, including a zip nested inside the download zip."""
from __future__ import annotations

import zipfile
from pathlib import Path


def safe_extract_zip(archive: zipfile.ZipFile, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    for member in archive.infolist():
        target = (root / member.filename).resolve()
        if not target.is_relative_to(root):
            raise ValueError(f"Unsafe path in model archive: {member.filename}")
    archive.extractall(root)


def unpack_model_archives(root: Path, *, max_depth: int = 3) -> None:
    """
    Open nested model zips.

    AutoML stores ``automl_predictor.zip`` as one object. The download helper
    wraps that object in a second zip, so ``predictor.pkl`` is still packed
    after a single extract.
    """
    for _ in range(max_depth):
        if any(root.rglob("predictor.pkl")):
            return
        packed = [path for path in root.rglob("*.zip") if path.is_file()]
        if not packed:
            return
        for zpath in packed:
            dest = zpath.with_suffix("")
            try:
                with zipfile.ZipFile(zpath) as archive:
                    safe_extract_zip(archive, dest)
            except zipfile.BadZipFile:
                continue
