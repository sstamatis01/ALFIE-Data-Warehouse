# AutoDW — localized stack (localhost)

This folder runs a **self-contained AutoDW system** for integration testing. It does **not** use `alfie.iti.gr` (that host is only for the separate ITI deployment via `docker-compose.deployment.yml` in the repo root).

## How images work (important)

This is **not** one giant container with everything inside. Docker Compose starts **several containers** on one private network:

```
┌─────────────────────────────────────────────────────────────────┐
│  docker network: autodw-network                                  │
│                                                                  │
│  mongodb   minio   zookeeper → kafka   graphdb                   │
│                              ↑                                   │
│                    api (autodw image)                            │
│                    bias-detector (same autodw image, diff command)│
│                    [automl-consumer] (optional profile)          │
└─────────────────────────────────────────────────────────────────┘
         │ ports published to your machine
         ▼
   localhost:8000  → API
   localhost:9092  → Kafka (for other stacks on the same host)
   localhost:9000  → MinIO
   localhost:7200  → GraphDB
```

### What is pushed to GitLab?

| Image | Registry | When |
|-------|----------|------|
| **`autodw`** (API + Python workers) | `gitlab.catalink.eu:5050/external/alfie_eu/alfie/autodw:1.0.0` | Git tag `v1.0.0` → CI build |
| MongoDB, MinIO, Kafka, GraphDB, Zookeeper | **Not** in GitLab — pulled from Docker Hub on `docker compose up` | Always |

So you **do not** get seven separate GitLab images. You get **one application image** plus a **compose file** that pulls standard infrastructure images and wires them together.

The same `autodw` image is used three times with different commands:

| Container | Command |
|-----------|---------|
| `api` | `uvicorn app.main:app` |
| `bias-detector` | `python kafka_bias_detector_consumer_example.py` |
| `automl-consumer` (optional) | `python kafka_automl_consumer_example_v3.py` |

### Inside the stack vs from outside

| Client | API | Kafka |
|--------|-----|-------|
| Containers **in** this compose file | `http://api:8000` | `kafka:29092` |
| Your browser / curl on the host | `http://localhost:8000` | `localhost:9092` |
| **Another** Docker Compose project on the same machine | `http://host.docker.internal:8000` | `host.docker.internal:9092` |

`KAFKA_ADVERTISED_HOST=localhost` in `.env` ensures Kafka metadata tells clients to use **localhost:9092**, not a remote hostname.

## Quick start (test after CI published `1.0.0`)

```bash
# 1) Config
cp autodw/.env.example autodw/.env
# Edit passwords if needed; keep KAFKA_ADVERTISED_HOST=localhost

# 2) Registry login (read access to alfie project)
docker login gitlab.catalink.eu:5050

# 3) Pull app image + start full stack (core: api + bias-detector + infra)
docker compose -f autodw/docker-compose.yaml --env-file autodw/.env pull api bias-detector
docker compose -f autodw/docker-compose.yaml --env-file autodw/.env up -d

# 4) Verify
docker compose -f autodw/docker-compose.yaml ps
curl -s http://localhost:8000/docs | head
```

Optional:

```bash
# Kafka UI
docker compose -f autodw/docker-compose.yaml --env-file autodw/.env --profile debug up -d

# AutoML consumer (needs tabular/vision services on host ports 8001/8002)
docker compose -f autodw/docker-compose.yaml --env-file autodw/.env --profile automl up -d
```

## Connect another component (e.g. Agentic Core orchestrator)

If orchestrator runs **on the host** (not in this compose file):

```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
API_BASE=http://localhost:8000
```

If orchestrator runs in **another Docker Compose** project, add to that compose file:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
environment:
  KAFKA_BOOTSTRAP_SERVERS: host.docker.internal:9092
  API_BASE: http://host.docker.internal:8000
```

Or attach both stacks to the same external network (advanced).

## Kafka topics (in-stack)

- `dataset-events` — produced by API on upload
- `bias-detection-trigger-events` — consumed by `bias-detector`
- `bias-detection-complete-events` — produced by bias worker
- `automl-trigger-events` / `automl-complete-events` — if automl profile is enabled

## Releasing a new `autodw` image (maintainers)

1. GitHub: set `DOCKER_REGISTRY_USERNAME` (variable) and `DOCKER_REGISTRY_PASSWORD` (secret).
2. Tag: `git tag v1.0.0 && git push origin v1.0.0`
3. CI pushes `autodw:1.0.0` and `autodw:latest`.
4. Testers set `AUTODW_VERSION=1.0.0` in `autodw/.env` and run `docker compose pull && up`.

## alfie.iti.gr vs this bundle

| | `autodw/` (this folder) | ITI server (`docker-compose.deployment.yml`) |
|--|-------------------------|-----------------------------------------------|
| Purpose | Local / partner integration | Production deployment |
| Kafka advertised | `localhost` | `alfie.iti.gr` |
| API path | `/` (direct :8000) | `/autodw` behind reverse proxy |

Do not mix the two `.env` files.
