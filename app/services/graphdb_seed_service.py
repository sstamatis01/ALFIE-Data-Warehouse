"""
Auto-create a GraphDB API config in MongoDB when the stack starts with empty configs.
"""

from __future__ import annotations

import logging
import os

from ..models.graphdb import GraphDBConfigResponse
from .graphdb_bootstrap import (
    auto_seed_enabled,
    build_config_create,
    fetch_repositories_with_retry,
    pick_repository_id,
    preferred_repository_env,
)
from .graphdb_service import graphdb_service

logger = logging.getLogger(__name__)


async def maybe_seed_graphdb_config() -> GraphDBConfigResponse | None:
    """
    Create a GraphDB config when graphdb_configs is empty and GraphDB has repositories.
    Returns the new config, or None if skipped.
    """
    if not auto_seed_enabled():
        logger.info("GraphDB auto-seed disabled (GRAPHDB_AUTO_SEED)")
        return None

    await graphdb_service.initialize()
    existing = await graphdb_service.collection.count_documents({})
    if existing > 0:
        logger.info("GraphDB already has %s config(s); skipping auto-seed", existing)
        return None

    try:
        repos = await fetch_repositories_with_retry()
    except Exception as e:
        logger.warning("GraphDB auto-seed skipped (cannot list repositories): %s", e)
        return None

    repo_id = pick_repository_id(repos, preferred_repository_env())
    if not repo_id:
        logger.warning(
            "GraphDB auto-seed skipped: no repositories (restore graphdb_init backup first)"
        )
        return None

    created_by = os.getenv("GRAPHDB_CONFIG_CREATED_BY", "autodw")
    config_data = build_config_create(repository_id=repo_id, created_by_label=created_by)

    try:
        created = await graphdb_service.create_config(config_data, created_by)
    except Exception as e:
        logger.warning("GraphDB auto-seed failed to create config: %s", e)
        return None

    try:
        test = await graphdb_service.test_connection(created.id)
        logger.info(
            "GraphDB connection test for config %s: success=%s",
            created.id,
            test.success,
        )
    except Exception as e:
        logger.warning("GraphDB post-seed connection test failed: %s", e)

    logger.info(
        "GraphDB config ready: id=%s repository=%s — partners: GET /graphdb/configs",
        created.id,
        created.repository_name,
    )
    return created
