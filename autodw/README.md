# AutoDW — GitLab integration package

This folder contains what integrators need to run **AutoDW** (ALFIE Data Warehouse) from the GitLab Container Registry, without building from source.

## Container image

| Item | Value |
|------|--------|
| Registry | `gitlab.catalink.eu:5050` |
| Image | `gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw` |
| Example tags | `1.0.0` (pinned), `latest` (newest release) |

Legacy partner image tag `kinit-test` referred to an earlier build; new releases use **semver** tags (`1.0.0`, `1.1.0`, …).

The same image runs:

- **API** — `uvicorn app.main:app`
- **bias-detector** — `python kafka_bias_detector_consumer_example.py`
- **automl-consumer** — `python kafka_automl_consumer_example_v3.py`

Concept drift is **not** included in this image workflow; run that script in a separate Python environment if needed.

## Quick start

1. Copy environment template:

   ```bash
   cp autodw/.env.example autodw/.env
   # Edit ports, PUBLIC_HOST, passwords, AUTODW_VERSION
   ```

2. Log in to the registry (credentials from your GitLab project):

   ```bash
   docker login gitlab.catalink.eu:5050
   ```

3. Start the stack:

   ```bash
   docker compose -f autodw/docker-compose.yaml --env-file autodw/.env up -d
   ```

4. Verify:

   ```bash
   docker compose -f autodw/docker-compose.yaml ps
   curl -s "http://localhost:${API_PORT:-8000}/docs" | head
   ```

When behind a reverse proxy at `https://<PUBLIC_HOST>/autodw`, set `ROOT_PATH=/autodw` in `.env`.

## Resource guidelines

| Component | Suggested minimum |
|-----------|-------------------|
| API + consumers | 2 GB RAM |
| MongoDB | 1 GB RAM, persistent volume |
| MinIO | 1 GB RAM, persistent volume for datasets |
| Kafka + Zookeeper | 2 GB RAM |
| GraphDB | 2 GB RAM (`GDB_HEAP_SIZE` / `GDB_MAX_MEM` default 1g each) |

Disk: plan for dataset storage in MinIO (size depends on uploads).

## Kafka integration

- **External clients** (orchestrator on host or another VM): `PUBLIC_HOST:9092` (must match `KAFKA_ADVERTISED_HOST`).
- **In-stack services**: `kafka:29092`.

Main topics: `dataset-events`, `bias-detection-trigger-events`, `bias-detection-complete-events`, `automl-trigger-events`, `automl-complete-events`.

## Releasing a new image (maintainers)

Releases are triggered by **git tags**, not by every merge to `main`.

1. Configure GitHub repository:
   - Variable: `DOCKER_REGISTRY_USERNAME`
   - Secret: `DOCKER_REGISTRY_PASSWORD` (GitLab deploy token or PAT with `write_registry`)

2. Tag and push:

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. GitHub Actions (`.github/workflows/docker-build-push.yml`) builds and pushes:

   - `gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw:1.0.0`
   - `gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw:latest`

The `v` prefix is stripped for registry tags (`v1.0.0` → `1.0.0`).

4. Update `AUTODW_VERSION` in deployment `.env` to the new semver.

## Files in this folder

| File | Purpose |
|------|---------|
| `.env.example` | Tunable ports, hosts, credentials for integration |
| `docker-compose.yaml` | Full stack using registry image (no local `build`) |
| `README.md` | This guide |

Source development still uses the repository root `docker-compose.yml` with `build: .`.
