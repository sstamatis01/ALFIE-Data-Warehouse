# GraphDB initial backup

Place your GraphDB backup archive here so the Docker stack initializes GraphDB with it on first run.

## Setup

1. **Copy your backup** into this directory:
   - Put `graphdb_backup_20260225_165121.tar.gz` (or your backup file) in this folder.
   - The file will be used only when the GraphDB data volume is empty (first run or after `docker compose down -v`).

2. **Build and start** (from the repo root):
   ```bash
   docker compose up -d graphdb
   ```
   On first start, the entrypoint will detect the empty data directory, extract the backup into GraphDB's data directory, then start GraphDB. Subsequent starts reuse the existing data and do not overwrite.

## Backup format

The `.tar.gz` should be an export of the GraphDB **data** directory (e.g. from another AutoDW/GraphDB instance). Supported layouts:

- Archive contents are the data directory contents (e.g. `repositories/`, etc.) → extracted directly into GraphDB data.
- Archive has a single top-level `data/` folder → its contents are copied into GraphDB data.
- Archive has a top-level `repositories/` folder → copied into GraphDB data.
- Archive has `home/data/` (full home export) → `home/data/` contents are copied into GraphDB data.

## SPARQL and API

After startup:

- **GraphDB Workbench:** http://localhost:7200  
- **SPARQL via Data Warehouse API:** use the `POST /graphdb/query` endpoint with a **GraphDB config** that points at this instance.

### Why `GET /graphdb/configs` returns `[]`

GraphDB **configs** are stored in **MongoDB** by the Data Warehouse API. They are not part of the GraphDB backup. The backup only restores the triple store (repositories and data). So after a fresh deploy you always start with no configs; you need to create one so the API knows how to connect to your GraphDB and which repository to use.

### 1. Discover your repository name

List repositories in your restored GraphDB:

```bash
curl -s -u admin:admin "http://localhost:7200/rest/repositories" | head -100
```

Or open http://localhost:7200 in a browser, go to **Setup** → **Repositories**, and note the **repository ID** (e.g. `etd-hub-kg`, `repo1`).

### 2. Create a GraphDB config in the Data Warehouse API

**Option A – helper script (from repo root)**

```bash
cd graphdb_init
sh create_graphdb_config.sh YOUR_REPO_ID your-user-id
```

If you omit `YOUR_REPO_ID`, the script tries to list repositories from GraphDB and use the first one. Example: `sh create_graphdb_config.sh etd-hub-kg default`.

**Option B – curl**

From the host (API on port 8000). Use **`http://graphdb:7200`** in the endpoints so that the API container can reach GraphDB on the Docker network. Replace `YOUR_REPO_ID` with the repository ID from step 1, and `your-user-id` with any string (e.g. `default`).

```bash
curl -X POST "http://localhost:8000/graphdb/configs?created_by=your-user-id" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Local GraphDB (restored backup)",
    "description": "GraphDB in Docker with initialized backup",
    "select_endpoint": "http://graphdb:7200/repositories/YOUR_REPO_ID",
    "update_endpoint": "http://graphdb:7200/repositories/YOUR_REPO_ID/statements",
    "username": "admin",
    "password": "admin",
    "repository_name": "YOUR_REPO_ID"
  }'
```

If the API runs **outside** Docker and talks to GraphDB on the host, use `http://localhost:7200` instead of `http://graphdb:7200` in both endpoints.

### 3. Run SPARQL via the API

Use the `config_id` returned when you created the config:

```bash
curl -X POST "http://localhost:8000/graphdb/query" \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "<paste-config_id-here>",
    "query": "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 10",
    "query_type": "SELECT"
  }'
```

Repository IDs and names inside the backup are preserved; the config’s `repository_name` and the endpoints must reference the same repository ID as in GraphDB.

## Note

Backup files (e.g. `*.tar.gz`) in this directory are ignored by git via `.gitignore` so large exports are not committed. Ensure the backup is present in this folder before the first `docker compose up` that starts GraphDB.
