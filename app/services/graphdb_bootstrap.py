"""
Shared helpers to create a GraphDB MongoDB config for Docker / AutoDW deploys.
Used by API auto-seed and scripts/init_graphdb_config.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, List, Optional
from urllib.parse import urljoin

import aiohttp

from ..models.graphdb import GraphDBConfigCreate

logger = logging.getLogger(__name__)

DEFAULT_PREFERRED_REPOS = ("etd-hub-kg-test", "etd-hub-kg")


def auto_seed_enabled() -> bool:
    return os.getenv("GRAPHDB_AUTO_SEED", "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def graphdb_rest_url() -> str:
    return os.getenv("GRAPHDB_REST_URL", "http://graphdb:7200").rstrip("/")


def graphdb_internal_host() -> str:
    return os.getenv("GRAPHDB_INTERNAL_HOST", "graphdb")


def graphdb_port() -> int:
    return int(os.getenv("GRAPHDB_PORT", "7200"))


def graphdb_credentials() -> tuple[str, str]:
    user = os.getenv("GDB_USER", "admin")
    password = os.getenv(
        "GDB_PASS",
        os.getenv("GDB_MASTER_PASSWORD", "admin"),
    )
    return user, password


def preferred_repository_env() -> Optional[str]:
    value = os.getenv("GRAPHDB_REPOSITORY", "").strip()
    return value or None


async def fetch_repositories(
    rest_url: str,
    username: str,
    password: str,
    *,
    timeout: int = 30,
) -> List[dict[str, Any]]:
    url = urljoin(rest_url + "/", "rest/repositories")
    auth = aiohttp.BasicAuth(username, password)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, auth=auth, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected GraphDB repositories response: {data!r}")
    return data


def pick_repository_id(
    repos: List[dict[str, Any]],
    preferred: Optional[str] = None,
) -> Optional[str]:
    ids = [r.get("id") for r in repos if r.get("id")]
    if not ids:
        return None

    if preferred:
        if preferred in ids:
            return preferred
        logger.warning(
            "GraphDB repository %r not found (available: %s); falling back",
            preferred,
            ", ".join(ids),
        )

    for candidate in DEFAULT_PREFERRED_REPOS:
        if candidate in ids:
            return candidate

    if len(ids) == 1:
        return ids[0]

    logger.warning(
        "Multiple GraphDB repositories (%s); using %s. Set GRAPHDB_REPOSITORY to choose.",
        ", ".join(ids),
        ids[0],
    )
    return ids[0]


def build_config_create(
    *,
    repository_id: str,
    internal_host: Optional[str] = None,
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    created_by_label: str = "autodw",
) -> GraphDBConfigCreate:
    host = internal_host or graphdb_internal_host()
    p = port if port is not None else graphdb_port()
    user, pwd = graphdb_credentials()
    if username is not None:
        user = username
    if password is not None:
        pwd = password

    base = f"http://{host}:{p}/repositories/{repository_id}"
    config_name = name or os.getenv("GRAPHDB_CONFIG_NAME", "AutoDW GraphDB (Docker)")
    return GraphDBConfigCreate(
        name=config_name,
        description=description
        or f"Auto-created for repository {repository_id} ({created_by_label})",
        select_endpoint=base,
        update_endpoint=f"{base}/statements",
        username=user,
        password=pwd,
        repository_name=repository_id,
    )


async def fetch_repositories_with_retry(
    *,
    max_attempts: int = 8,
    delay_seconds: float = 5.0,
) -> List[dict[str, Any]]:
    rest_url = graphdb_rest_url()
    username, password = graphdb_credentials()
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            repos = await fetch_repositories(rest_url, username, password)
            logger.info(
                "GraphDB REST reachable (%s); %s repositories",
                rest_url,
                len(repos),
            )
            return repos
        except Exception as e:
            last_error = e
            if attempt < max_attempts:
                logger.info(
                    "GraphDB not ready (attempt %s/%s): %s; retry in %ss",
                    attempt,
                    max_attempts,
                    e,
                    delay_seconds,
                )
                await asyncio.sleep(delay_seconds)
            else:
                logger.warning(
                    "GraphDB REST unavailable after %s attempts: %s",
                    max_attempts,
                    e,
                )
    if last_error:
        raise last_error
    return []
