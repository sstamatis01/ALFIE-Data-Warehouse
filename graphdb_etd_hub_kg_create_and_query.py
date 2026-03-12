#!/usr/bin/env python3
"""
Create a GraphDB config for repository 'etd-hub-kg-test' and run example SPARQL queries
via the Data Warehouse API.

Usage:
  API_BASE=http://localhost:8000 python graphdb_etd_hub_kg_create_and_query.py

Requires: requests
"""

import os
import json
import sys

try:
    import requests
except ImportError:
    print("This script requires the 'requests' library. Install with: pip install requests")
    sys.exit(1)

API_BASE = os.getenv("API_BASE", "https://alfie.iti.gr/autodw")
REPO_NAME = "etd-hub-kg-test"
CREATED_BY = os.getenv("CREATED_BY", "default")
# Use graphdb:7200 so the API container (in Docker) can reach GraphDB; override if API runs elsewhere
GRAPHDB_HOST = os.getenv("GRAPHDB_HOST", "graphdb")
GRAPHDB_PORT = os.getenv("GRAPHDB_PORT", "7200")
GDB_USER = os.getenv("GDB_USER", "admin")
GDB_PASS = os.getenv("GDB_PASS", "admin")


def create_config() -> str:
    """Create or reuse a GraphDB config for etd-hub-kg-test. Returns config_id."""
    select_endpoint = f"http://{GRAPHDB_HOST}:{GRAPHDB_PORT}/repositories/{REPO_NAME}"
    update_endpoint = f"http://{GRAPHDB_HOST}:{GRAPHDB_PORT}/repositories/{REPO_NAME}/statements"

    payload = {
        "name": "ETD-Hub KG (etd-hub-kg-test)",
        "description": f"GraphDB repository {REPO_NAME} for ETD-Hub knowledge graph",
        "select_endpoint": select_endpoint,
        "update_endpoint": update_endpoint,
        "username": GDB_USER,
        "password": GDB_PASS,
        "repository_name": REPO_NAME,
    }

    r = requests.post(
        f"{API_BASE}/graphdb/configs",
        params={"created_by": CREATED_BY},
        json=payload,
        timeout=30,
    )

    if r.status_code == 200:
        data = r.json()
        config_id = data.get("id")
        print(f"Created GraphDB config: {data.get('name')} (id={config_id})")
        return config_id

    if r.status_code == 409:
        # Config with this name already exists; find by repository_name
        list_r = requests.get(f"{API_BASE}/graphdb/configs", params={"skip": 0, "limit": 100}, timeout=10)
        list_r.raise_for_status()
        for c in list_r.json():
            if c.get("repository_name") == REPO_NAME:
                config_id = c.get("id")
                print(f"Using existing GraphDB config for {REPO_NAME} (id={config_id})")
                return config_id
        print("A config with the same name exists but no config found for repository_name=%s" % REPO_NAME)
    else:
        print(f"Failed to create config: {r.status_code} - {r.text[:500]}")

    raise RuntimeError("Could not obtain config_id for %s" % REPO_NAME)


def run_sparql(config_id: str, query: str, query_type: str = "SELECT") -> dict:
    """Run a SPARQL query via the Data Warehouse API."""
    r = requests.post(
        f"{API_BASE}/graphdb/query",
        json={
            "config_id": config_id,
            "query": query,
            "query_type": query_type,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


def main():
    print("=" * 60)
    print("GraphDB config + SPARQL for etd-hub-kg-test")
    print("API_BASE =", API_BASE)
    print("=" * 60)

    config_id = create_config()

    # Optional: test connection
    try:
        test_r = requests.post(
            f"{API_BASE}/graphdb/configs/{config_id}/test",
            timeout=15,
        )
        if test_r.status_code == 200 and test_r.json().get("success"):
            print("Connection test: OK")
        else:
            print("Connection test:", test_r.json() if test_r.ok else test_r.text[:200])
    except Exception as e:
        print("Connection test skipped:", e)

    queries = [
        (
            "Count triples",
            "SELECT (COUNT(*) AS ?count) WHERE { ?s ?p ?o }",
        ),
        (
            "Sample triples",
            "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10",
        ),
        (
            "Distinct predicates",
            "SELECT DISTINCT ?p WHERE { ?s ?p ?o } ORDER BY ?p LIMIT 20",
        ),
    ]

    for title, query in queries:
        print("\n" + "-" * 60)
        print("Query:", title)
        print("-" * 60)
        try:
            result = run_sparql(config_id, query)
            if result.get("success"):
                print("Execution time: %.3f s" % result.get("execution_time", 0))
                data = result.get("data")
                if data:
                    print(json.dumps(data, indent=2, default=str))
                else:
                    print("(no data key in response)")
            else:
                print("Error:", result.get("error", "unknown"))
        except requests.exceptions.RequestException as e:
            print("Request failed:", e)
        except Exception as e:
            print("Error:", e)

    print("\n" + "=" * 60)
    print("Done. config_id =", config_id)
    print("=" * 60)


if __name__ == "__main__":
    main()
