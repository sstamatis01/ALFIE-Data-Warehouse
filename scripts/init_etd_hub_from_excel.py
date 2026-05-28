#!/usr/bin/env python3
"""
Import ETD-Hub MongoDB data from an Excel export (GET /etd-hub/export/excel format).

Usage (API must be running, or use upload-excel via curl instead):

  python scripts/init_etd_hub_from_excel.py
  python scripts/init_etd_hub_from_excel.py --file etd_hub_init/etd_hub_seed.xlsx

Direct import without HTTP (needs MongoDB env / same deps as API):

  python scripts/init_etd_hub_from_excel.py --direct
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("init_etd_hub_from_excel")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = REPO_ROOT / "etd_hub_init" / "etd_hub_seed.xlsx"
DEFAULT_API = os.getenv("API_BASE", "http://localhost:8000")


def import_via_api(api_base: str, excel_path: Path, clear_existing: bool) -> int:
    url = f"{api_base.rstrip('/')}/etd-hub/import/upload-excel"
    params = {"clear_existing": str(clear_existing).lower()}
    with excel_path.open("rb") as f:
        r = requests.post(
            url,
            params=params,
            files={"file": (excel_path.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=120,
        )
    r.raise_for_status()
    body = r.json()
    logger.info("Import response: %s", body)
    return body.get("total_imported", 0)


async def import_direct(excel_path: Path, clear_existing: bool) -> int:
    from app.api.etd_hub_import import importer
    from app.core.database import connect_to_mongo, close_mongo_connection

    await connect_to_mongo()
    try:
        await importer.initialize()
        results = await importer.import_from_excel_path(
            str(excel_path), clear_existing=clear_existing
        )
        total = sum(results.values())
        logger.info("Imported %s records: %s", total, results)
        return total
    finally:
        await close_mongo_connection()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Seed ETD-Hub from Excel export")
    p.add_argument("--file", type=Path, default=DEFAULT_FILE, help="Path to .xlsx seed")
    p.add_argument("--api-base", default=DEFAULT_API)
    p.add_argument("--direct", action="store_true", help="Import via MongoDB (no HTTP)")
    p.add_argument(
        "--no-clear",
        action="store_true",
        help="Do not clear existing ETD-Hub collections before import",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.file.is_file():
        logger.error("Excel file not found: %s", args.file)
        return 1

    clear_existing = not args.no_clear
    try:
        if args.direct:
            total = asyncio.run(import_direct(args.file, clear_existing))
        else:
            total = import_via_api(args.api_base, args.file, clear_existing)
    except requests.RequestException as e:
        logger.error("API import failed (is the stack up at %s?): %s", args.api_base, e)
        return 1
    except Exception as e:
        logger.error("Import failed: %s", e, exc_info=True)
        return 1

    logger.info("Done. Total records: %s", total)
    logger.info("Check: curl %s/etd-hub/stats/overview", args.api_base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
