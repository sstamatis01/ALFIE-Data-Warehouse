"""
Seed ETD-Hub MongoDB collections from a bundled Excel export on first deploy.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from ..api.etd_hub_import import importer

logger = logging.getLogger(__name__)

DEFAULT_SEED_PATH = Path("/app/etd_hub_init/etd_hub_seed.xlsx")


def _auto_seed_enabled() -> bool:
    return os.getenv("ETD_HUB_AUTO_SEED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def resolve_seed_path() -> Path | None:
    explicit = os.getenv("ETD_HUB_SEED_PATH", "").strip()
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    if DEFAULT_SEED_PATH.is_file():
        return DEFAULT_SEED_PATH
    # Local dev without Docker image layout
    repo_seed = Path(__file__).resolve().parents[2] / "etd_hub_init" / "etd_hub_seed.xlsx"
    if repo_seed.is_file():
        return repo_seed
    return None


async def maybe_seed_etd_hub_from_excel() -> dict | None:
    """
    Import bundled Excel when ETD-Hub collections are empty.
    Returns import results dict, or None if seed was skipped.
    """
    if not _auto_seed_enabled():
        logger.info("ETD-Hub auto-seed disabled (ETD_HUB_AUTO_SEED)")
        return None

    seed_path = resolve_seed_path()
    if not seed_path:
        logger.info("No ETD-Hub seed Excel found; skipping auto-seed")
        return None

    await importer.initialize()
    existing = await importer.themes_collection.count_documents({})
    if existing > 0:
        logger.info(
            "ETD-Hub already has %s themes; skipping auto-seed from %s",
            existing,
            seed_path,
        )
        return None

    logger.info("Seeding ETD-Hub from %s", seed_path)
    results = await importer.import_from_excel_path(
        str(seed_path), clear_existing=False
    )
    total = sum(results.values())
    logger.info("ETD-Hub auto-seed completed: %s records (%s)", total, results)
    return results
