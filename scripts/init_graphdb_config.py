#!/usr/bin/env python3
"""
Optional: bootstrap a GraphDB config via HTTP (for hosts without the autodw image).

Docker/registry deploys auto-seed on API startup (GRAPHDB_AUTO_SEED=true).
After compose up, partners only need:

  curl -s http://localhost:8000/graphdb/configs

Use the "id" field from the JSON response — do not reuse IDs from other environments.

This script is for manual re-runs or local debugging when the API is already up.

Environment overrides: API_BASE, GRAPHDB_URL, GDB_USER, GDB_PASS, API_GRAPHDB_HOST
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any
from urllib.parse import urljoin

import requests
from requests.auth import HTTPBasicAuth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("init_graphdb_config")

DEFAULT_API = os.getenv("API_BASE", "http://localhost:8000")
DEFAULT_GRAPHDB = os.getenv("GRAPHDB_URL", "http://localhost:7200")
DEFAULT_API_GRAPHDB_HOST = os.getenv("API_GRAPHDB_HOST", "graphdb")
DEFAULT_GDB_USER = os.getenv("GDB_USER", "admin")
DEFAULT_GDB_PASS = os.getenv("GDB_PASS", os.getenv("GDB_MASTER_PASSWORD", "admin"))
DEFAULT_CREATED_BY = os.getenv("GRAPHDB_CONFIG_CREATED_BY", "default")
DEFAULT_CONFIG_NAME = os.getenv(
    "GRAPHDB_CONFIG_NAME", "AutoDW local GraphDB"
)


def list_graphdb_repositories(
    graphdb_url: str, username: str, password: str
) -> list[dict[str, Any]]:
    url = urljoin(graphdb_url.rstrip("/") + "/", "rest/repositories")
    logger.info("Listing GraphDB repositories: %s", url)
    r = requests.get(url, auth=HTTPBasicAuth(username, password), timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError(f"Unexpected repositories response: {data!r}")
    return data


def pick_repository_id(
    repos: list[dict[str, Any]], preferred: str | None
) -> str:
    if preferred:
        ids = {r.get("id") for r in repos}
        if preferred not in ids:
            available = ", ".join(sorted(i for i in ids if i))
            raise SystemExit(
                f"Repository '{preferred}' not found. Available: {available or '(none)'}"
            )
        return preferred
    if not repos:
        raise SystemExit(
            "No repositories in GraphDB. Create one at http://localhost:7200 "
            "(Setup → Repositories) or restore a GraphDB backup, then re-run."
        )
    if len(repos) == 1:
        return repos[0]["id"]
    ids = [r.get("id", "?") for r in repos]
    logger.warning(
        "Multiple repositories (%s); using first: %s. Pass --repository to choose.",
        ", ".join(ids),
        ids[0],
    )
    return repos[0]["id"]


def build_config_payload(
    *,
    repository_id: str,
    api_graphdb_host: str,
    graphdb_port: int,
    username: str,
    password: str,
    name: str,
    description: str | None,
) -> dict[str, Any]:
    base = f"http://{api_graphdb_host}:{graphdb_port}/repositories/{repository_id}"
    return {
        "name": name,
        "description": description
        or f"GraphDB repository {repository_id} (created by init_graphdb_config.py)",
        "select_endpoint": base,
        "update_endpoint": f"{base}/statements",
        "username": username,
        "password": password,
        "repository_name": repository_id,
    }


def list_api_configs(api_base: str) -> list[dict[str, Any]]:
    url = f"{api_base.rstrip('/')}/graphdb/configs"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def create_config(
    api_base: str, created_by: str, payload: dict[str, Any]
) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}/graphdb/configs"
    r = requests.post(
        url,
        params={"created_by": created_by},
        json=payload,
        timeout=30,
    )
    if r.status_code == 409:
        logger.error("Config name already exists. Response: %s", r.text)
        raise SystemExit(1)
    r.raise_for_status()
    return r.json()


def test_config(api_base: str, config_id: str) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}/graphdb/configs/{config_id}/test"
    r = requests.post(url, timeout=60)
    r.raise_for_status()
    return r.json()


def sample_query(api_base: str, config_id: str) -> dict[str, Any]:
    url = f"{api_base.rstrip('/')}/graphdb/query"
    body = {
        "config_id": config_id,
        "query": "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5",
        "query_type": "SELECT",
    }
    r = requests.post(url, json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create a GraphDB config in AutoDW (MongoDB) for Docker GraphDB"
    )
    p.add_argument("--api-base", default=DEFAULT_API, help="AutoDW API base URL")
    p.add_argument(
        "--graphdb-url",
        default=DEFAULT_GRAPHDB,
        help="GraphDB URL reachable from this machine (for listing repos)",
    )
    p.add_argument(
        "--api-graphdb-host",
        default=DEFAULT_API_GRAPHDB_HOST,
        help="Hostname the API container uses to reach GraphDB (default: graphdb)",
    )
    p.add_argument(
        "--graphdb-port",
        type=int,
        default=int(os.getenv("GRAPHDB_PORT", "7200")),
        help="GraphDB port inside Docker network",
    )
    p.add_argument("--repository", default=None, help="Repository ID (e.g. etd-hub-kg-test)")
    p.add_argument("--created-by", default=DEFAULT_CREATED_BY)
    p.add_argument("--name", default=DEFAULT_CONFIG_NAME)
    p.add_argument("--username", default=DEFAULT_GDB_USER)
    p.add_argument("--password", default=DEFAULT_GDB_PASS)
    p.add_argument(
        "--list-repositories",
        action="store_true",
        help="List GraphDB repositories and exit",
    )
    p.add_argument(
        "--list-configs",
        action="store_true",
        help="List existing API GraphDB configs and exit",
    )
    p.add_argument(
        "--test",
        action="store_true",
        help="POST /graphdb/configs/{id}/test after create",
    )
    p.add_argument(
        "--sample-query",
        action="store_true",
        help="Run a small SELECT via /graphdb/query after create",
    )
    p.add_argument(
        "--skip-create-if-configs-exist",
        action="store_true",
        help="Exit 0 without creating if any config already exists",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    api_base = args.api_base.rstrip("/")

    try:
        if args.list_configs:
            configs = list_api_configs(api_base)
            print(json.dumps(configs, indent=2, default=str))
            if not configs:
                logger.info("No GraphDB configs in MongoDB (expected on fresh deploy).")
            return 0

        repos = list_graphdb_repositories(
            args.graphdb_url, args.username, args.password
        )
        if args.list_repositories:
            for r in repos:
                print(f"  {r.get('id')}: {r.get('title', r.get('id'))}")
            return 0

        if args.skip_create_if_configs_exist:
            existing = list_api_configs(api_base)
            if existing:
                c = existing[0]
                logger.info(
                    "Config already exists: id=%s repository_name=%s",
                    c.get("id"),
                    c.get("repository_name"),
                )
                print(f"GRAPHDB_CONFIG_ID={c.get('id')}")
                return 0

        repo_id = pick_repository_id(repos, args.repository)
        payload = build_config_payload(
            repository_id=repo_id,
            api_graphdb_host=args.api_graphdb_host,
            graphdb_port=args.graphdb_port,
            username=args.username,
            password=args.password,
            name=args.name,
            description=None,
        )

        logger.info("Creating config for repository %s ...", repo_id)
        logger.info(
            "API will use endpoints: %s", payload["select_endpoint"]
        )
        created = create_config(api_base, args.created_by, payload)
        config_id = created["id"]
        logger.info("Created GraphDB config id=%s", config_id)

        print()
        print("=== Use this config ID in your integration ===")
        print(f"GRAPHDB_CONFIG_ID={config_id}")
        print()
        print("Verify:")
        print(f"  curl -s {api_base}/graphdb/configs/{config_id}")
        print(f"  curl -s -X POST {api_base}/graphdb/configs/{config_id}/test")
        print()

        if args.test:
            result = test_config(api_base, config_id)
            logger.info("Connection test: %s", json.dumps(result, indent=2, default=str))
            if not result.get("success"):
                logger.error("Connection test failed — check endpoints and credentials.")
                return 1

        if args.sample_query:
            result = sample_query(api_base, config_id)
            logger.info("Sample query: success=%s", result.get("success"))
            if not result.get("success"):
                logger.error("Sample query failed: %s", result.get("error"))
                return 1

        return 0

    except requests.HTTPError as e:
        logger.error(
            "HTTP error %s: %s",
            e.response.status_code if e.response is not None else "?",
            e.response.text if e.response is not None else e,
        )
        if e.response is not None and e.response.status_code == 404:
            logger.error(
                "404 usually means the config ID does not exist in THIS MongoDB. "
                "Run this script on the target stack; do not reuse IDs from other environments."
            )
        return 1
    except requests.RequestException as e:
        logger.error("Request failed (is the stack up?): %s", e)
        return 1
    except SystemExit as code:
        if isinstance(code.code, int):
            return code.code
        return 1


if __name__ == "__main__":
    sys.exit(main())
