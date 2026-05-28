# AutoDW — localized stack (localhost)

Self-contained AutoDW for **partner / local integration**. Not for `alfie.iti.gr` production (use repo-root `docker-compose.deployment.yml` there).

## Folder contents

| File | Purpose |
|------|---------|
| `docker-compose.yaml` | Full stack: MongoDB, MinIO, Kafka, GraphDB, API, bias-detector, automl-consumer |
| `.env.example` | Template — copy to `.env` and set passwords |
| `.env` | Your local config (create from example; do not commit) |
| `README.md` | This guide |

**Repo-root dependencies** (paths relative to `autodw/` in compose):

| Path | Required for | In registry image? |
|------|----------------|-------------------|
| `../graphdb_init/graphdb_backup_*.tar.gz` | GraphDB triple-store on first start | No — mount from host |
| `../graphdb_init/entrypoint.sh` | Backup restore entrypoint | No — mount from host |
| `../etd_hub_init/etd_hub_seed.xlsx` | ETD-Hub forum data (optional mount) | Yes in `autodw` **≥ 1.0.3** |

Clone the **full repository** (not only `autodw/`) so GraphDB backup restore works.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  docker network: autodw-network                                  │
│  mongodb   minio   zookeeper → kafka   graphdb                   │
│                              ↑                                   │
│                    api (autodw image)                            │
│                    bias-detector / automl-consumer               │
└─────────────────────────────────────────────────────────────────┘
         │ localhost
         ▼
   :8000 API   :9092 Kafka   :9000 MinIO   :7200 GraphDB
```

| Image | Source |
|-------|--------|
| `autodw` (API + workers) | GitLab `gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw` |
| MongoDB, MinIO, Kafka, GraphDB, Zookeeper | Docker Hub |

Same `autodw` image runs as `api`, `bias-detector`, and `automl-consumer` with different commands.

## Quick start (registry `1.0.3` or `latest`)

From **repo root**:

```bash
cp autodw/.env.example autodw/.env
# Edit passwords; ensure graphdb_init/graphdb_backup_*.tar.gz exists

docker login gitlab.catalink.eu:5050

docker compose -f autodw/docker-compose.yaml --env-file autodw/.env pull
docker compose -f autodw/docker-compose.yaml --env-file autodw/.env up -d --no-build
```

`--no-build` uses the pulled registry image. Omit it and use `up -d --build` only when developing API code in this repo.

### Verify (fresh volumes)

```bash
docker compose -f autodw/docker-compose.yaml --env-file autodw/.env ps
docker logs autodw-api 2>&1 | grep -iE "ETD-Hub|GraphDB|seed"

curl -s http://localhost:8000/health
curl -s http://localhost:8000/etd-hub/stats/overview
curl -s http://localhost:8000/graphdb/configs
curl -s -u admin:YOUR_GDB_PASSWORD http://localhost:7200/rest/repositories
```

Expected on first start:

- **ETD-Hub:** non-zero themes/questions (Excel auto-seed when `etd_themes` was empty)
- **GraphDB configs:** one entry with `"status":"active"` — use its `"id"` in your app
- **GraphDB repos:** e.g. `etd-hub-kg-test` after backup restore

API docs: http://localhost:8000/docs

### Reset and re-test

```bash
docker compose -f autodw/docker-compose.yaml --env-file autodw/.env down -v
docker compose -f autodw/docker-compose.yaml --env-file autodw/.env up -d --no-build
```

## First-time initialization (automatic)

| Layer | When it runs | Skip when |
|-------|----------------|-----------|
| GraphDB backup → volume | First GraphDB start, empty data dir | Repositories already exist |
| ETD-Hub Excel → Mongo | API start, `ETD_HUB_AUTO_SEED=true`, empty `etd_themes` | Themes already in Mongo |
| GraphDB config → Mongo | API start, `GRAPHDB_AUTO_SEED=true`, empty `graphdb_configs` | Config already in Mongo |

Set `ETD_HUB_AUTO_SEED=false` or `GRAPHDB_AUTO_SEED=false` in `autodw/.env` to disable.

**Get GraphDB `config_id` after deploy:**

```bash
curl -s http://localhost:8000/graphdb/configs
```

Do not reuse config IDs from other environments.

## Environment variables

All variables below can be set in `autodw/.env`. Compose passes defaults for seed-related keys even if omitted from `.env` (see `docker-compose.yaml` `api.environment`).

| Variable | Default | Role |
|----------|---------|------|
| `AUTODW_IMAGE` / `AUTODW_VERSION` | `…/autodw` / `1.0.3` | Registry image |
| `KAFKA_ADVERTISED_HOST` | `localhost` | External Kafka clients |
| `ROOT_PATH` | empty | Set `/autodw` only behind reverse proxy |
| `ETD_HUB_AUTO_SEED` | `true` | Import bundled Excel when forum DB empty |
| `ETD_HUB_SEED_PATH` | `/app/etd_hub_init/etd_hub_seed.xlsx` | Seed file path in container |
| `GRAPHDB_AUTO_SEED` | `true` | Create Mongo GraphDB config when empty |
| `GRAPHDB_REPOSITORY` | `etd-hub-kg-test` | Target repository ID |
| `GDB_MASTER_PASSWORD` | — | GraphDB admin password (graphdb + API `GDB_PASS`) |
| `GRAPHDB_REST_URL` | `http://graphdb:7200` | API lists repos at startup |

Full list: `autodw/.env.example`.

## ETD-Hub (forum data)

- Seed file: `etd_hub_init/etd_hub_seed.xlsx` (production export format)
- Update for next release: replace file, rebuild/push `autodw` — see [etd_hub_init/README.md](../etd_hub_init/README.md)
- Manual re-import: `POST /etd-hub/import/upload-excel`

## GraphDB

- **Triple store:** place `graphdb_backup_*.tar.gz` in `graphdb_init/` — see [graphdb_init/README.md](../graphdb_init/README.md)
- **API config:** auto-created; optional script `python scripts/init_graphdb_config.py` for debugging

## Connect other components

**On host:**

```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
API_BASE=http://localhost:8000
```

**Another Docker Compose project:**

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
environment:
  KAFKA_BOOTSTRAP_SERVERS: host.docker.internal:9092
  API_BASE: http://host.docker.internal:8000
```

## Kafka topics

- `dataset-events` — API uploads
- `bias-detection-trigger-events` / `bias-detection-complete-events`
- `automl-trigger-events` / `automl-complete-events` (automl-consumer)

Optional: `docker compose ... --profile debug up -d` for Kafka UI on port `8081`.

## Releasing `autodw` (maintainers)

**CI (tag → GitLab):**

```bash
git tag v1.0.3 && git push origin v1.0.3
```

Pushes `…/autodw:1.0.3` and `…/autodw:latest` via `.github/workflows/docker-build-push.yml`.

**Manual push** (if that is your process):

```bash
docker build -t gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw:1.0.3 \
             -t gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw:latest .
docker push gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw:1.0.3
docker push gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw:latest
```

## Production redeploy (alfie.iti.gr)

Auto-seed is idempotent. Redeploying a new API image against **existing** Mongo/GraphDB volumes does not overwrite ETD-Hub or GraphDB configs.

`docker-compose.deployment.yml` sets `ETD_HUB_AUTO_SEED=false` and `GRAPHDB_AUTO_SEED=false` on the ITI API as an extra safeguard.

| | `autodw/` (this folder) | ITI (`docker-compose.deployment.yml`) |
|--|-------------------------|----------------------------------------|
| Purpose | Local / partner | Production |
| Kafka advertised | `localhost` | `alfie.iti.gr` |
| API URL | `http://localhost:8000` | `https://alfie.iti.gr/autodw` |

Do not copy production `.env` into `autodw/.env`.

## Older registry tags

Tags **before 1.0.3** lack bundled ETD-Hub seed and auto-config code. Use `AUTODW_VERSION=1.0.3` (or `latest`) or `docker compose ... up -d --build` from a full repo clone.
