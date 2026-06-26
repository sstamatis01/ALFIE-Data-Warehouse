#!/usr/bin/env python3
"""
Ingest datasets into the AutoDW public catalog.

This script uploads each file in a local folder to:
  POST /datasets/public/upload

It intentionally does NOT trigger Kafka `dataset-events` (pipeline starts only after a user imports).

Examples:
  python scripts/ingest_public_datasets.py --api-base http://localhost:8000 --dir ./summer_school_datasets
  python scripts/ingest_public_datasets.py --api-base https://alfie.iti.gr/autodw --dir C:\\data\\summer_school
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import mimetypes
import requests


DEFAULT_EXTS = [
    ".csv",
    ".xls",
    ".xlsx",
    ".json",
    ".parquet",
    ".tsv",
    ".txt",
    ".zip",
]


def iter_files(root: Path, *, exts: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        if exts and p.suffix.lower() not in exts:
            continue
        out.append(p)
    return sorted(out)


def guess_content_type(p: Path) -> str:
    ct, _ = mimetypes.guess_type(str(p))
    return ct or "application/octet-stream"


def main() -> int:
    ap = argparse.ArgumentParser(description="Upload local files to AutoDW public dataset catalog")
    ap.add_argument("--api-base", required=True, help="AutoDW API base (e.g. http://localhost:8000)")
    ap.add_argument("--dir", required=True, help="Directory containing dataset files")
    ap.add_argument("--tags", default="summer-school,public", help="Comma-separated tags to attach")
    ap.add_argument("--public-source", default=None, help="Optional provenance string for all uploads")
    ap.add_argument(
        "--ext",
        action="append",
        default=None,
        help="File extension filter (repeatable). If omitted, uses a default list.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be uploaded without calling the API",
    )
    args = ap.parse_args()

    root = Path(args.dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    exts = [e.lower() if e.startswith(".") else ("." + e.lower()) for e in (args.ext or DEFAULT_EXTS)]
    files = iter_files(root, exts=exts)
    if not files:
        print(f"No files found under {root} for extensions: {exts}")
        return 2

    url = args.api_base.rstrip("/") + "/datasets/public/upload"
    print(f"Uploading {len(files)} file(s) to {url}")

    for p in files:
        if args.dry_run:
            print(f"[dry-run] {p}")
            continue

        dataset_id = p.stem.replace(" ", "_")
        name = p.stem
        ct = guess_content_type(p)
        with p.open("rb") as f:
            files_m = {"file": (p.name, f, ct)}
            data = {
                "dataset_id": dataset_id,
                "name": name,
                "description": f"Summer school public dataset: {p.name}",
                "tags": args.tags,
            }
            if args.public_source:
                data["public_source"] = args.public_source
            r = requests.post(url, files=files_m, data=data, timeout=300)
        r.raise_for_status()
        j = r.json()
        print(f"OK {p.name} -> dataset_id={j.get('dataset_id')} version={j.get('version')} file_type={j.get('file_type')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

