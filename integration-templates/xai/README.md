# XAI — GitLab integration package (template)

Copy this folder into the **XAI repository** (e.g. rename to `xai/` at repo root).  
Adjust paths in `docker-compose.yaml` if your entrypoint scripts live elsewhere.

## How XAI differs from AutoDW

| | **AutoDW** (`autodw/`) | **XAI** (this template) |
|--|------------------------|---------------------------|
| Registry image | `.../alfie/autodw:TAG` | `.../alfie/xai:TAG` |
| What the image runs | API + bias/automl workers | 2 Flask apps + Kafka consumer |
| Bundled infra | Mongo, MinIO, Kafka, GraphDB | **None** — uses existing AutoDW |
| Exposed ports | `8000`, `9092`, … | `5010`, `5001` |
| Kafka topic in | — | `xai-trigger-events` |
| Kafka topic out | — | `xai-complete-events` / DW `xai-events` |

XAI is a **satellite module**: it does not replace AutoDW.

```
  Agentic Core  ──► xai-trigger-events ──►  XAI consumer
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │  xai-network              │                           │
                    │  :5010 explain-model      │  :5001 analyze-data       │
                    └───────────────────────────┴───────────────────────────┘
                                                │
                    API_BASE ───────────────────► AutoDW :8000 (upload report)
                    KAFKA ◄──────────────────────  localhost:9092 (triggers)
```

## What to push to GitLab

One image, three containers (same pattern as AutoDW using one image multiple times):

| Container | Typical command / role |
|-----------|-------------------------|
| `universal-model-explainability` | `python flexible-scripts/universal_model_explainability.py` |
| `flexible-data-interpretability` | `python flexible-scripts/flexible_data_interpretability.py` |
| `kafka-xai-consumer` | `python scripts/kafka_call.py` (or your consumer script) |

**Registry path (ALFIE convention):**

```text
gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:1.0.0
```

## Build and push (manual)

From XAI repo root (where `Dockerfile` / `Dockerfile.xai-services` lives):

```bash
docker login gitlab.catalink.eu:5050 -u <user> --password-stdin

docker build -f Dockerfile.xai-services -t gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:1.0.0 .
docker push gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:1.0.0

docker tag  gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:1.0.0 \
            gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:latest
docker push gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:latest
```

## Pull and run (integration test)

**Prerequisite:** AutoDW stack running (`autodw/` or deployment) with Kafka on `localhost:9092` and API on `localhost:8000`.

```bash
cp .env.example .env
docker login gitlab.catalink.eu:5050

docker compose -f docker-compose.yaml --env-file .env pull
docker compose -f docker-compose.yaml --env-file .env up -d
docker compose -f docker-compose.yaml ps
```

**Health checks:**

```bash
curl -s http://localhost:5010/health
curl -s http://localhost:5001/health
```

**End-to-end:** produce a message on `xai-trigger-events` (via Agentic Core or console producer) and confirm a report appears in AutoDW / `xai-complete-events`.

## Environment variables (partner-facing)

| Variable | Purpose |
|----------|---------|
| `API_BASE` | AutoDW API URL for dataset/model download and report upload |
| `KAFKA_BOOTSTRAP_SERVERS` | Broker for trigger events |
| `KAFKA_XAI_TRIGGER_TOPIC` | Default `xai-trigger-events` |
| `KAFKA_CONSUMER_GROUP` | Default `xai-consumer` |
| `UNIVERSAL_MODEL_EXPLAINABILITY_URL` | In-stack URL to :5010 service |
| `FLEXIBLE_DATA_INTERPRETABILITY_URL` | In-stack URL to :5001 service |

Use `host.docker.internal` when XAI compose and AutoDW compose are **separate** projects on the same host. Use `http://api:8000` and `kafka:29092` only if both stacks share a Docker network.

## GitHub Actions (optional)

Add `.github/workflows/docker-build-push.yml` in the XAI repo:

```yaml
env:
  REGISTRY: gitlab.catalink.eu:5050
  IMAGE_PREFIX: gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai

# on push tags v*.*.* → build with Dockerfile.xai-services, push :semver and :latest
```

Secrets: same `DOCKER_REGISTRY_USERNAME` / `DOCKER_REGISTRY_PASSWORD` as AutoDW.

## Checklist before switching to the XAI repo

- [ ] Confirm Dockerfile name (`Dockerfile.xai-services` vs `Dockerfile`)
- [ ] Confirm consumer entrypoint (`scripts/kafka_call.py` vs `kafka_xai_consumer_example_v2.py`)
- [ ] Remove `alfie.iti.gr` defaults from Dockerfile/compose in XAI repo
- [ ] Copy this folder → `xai/` in XAI repo; fix `command:` paths if needed
- [ ] Add `.dockerignore` (exclude `.venv`, `reports/`, large test data)
- [ ] Build/push `xai:1.0.0` to GitLab
- [ ] Email ALFIE team: image URL + attach `docker-compose.yaml` + `.env.example` + this README

## What to send ALFIE integration team

> **Module:** `xai`  
> **Image:** `gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:1.0.0`  
> **Depends on:** AutoDW API (`API_BASE`) and Kafka (`xai-trigger-events`)  
> **Exposes:** HTTP `5010` (model explainability), `5001` (data interpretability)  
> **Compose:** `xai/docker-compose.yaml`  
> **Env template:** `xai/.env.example`  
> **RAM:** ~2–4 GB for consumer + Flask workers (SHAP/matplotlib)

## Resource guidelines

| Component | Suggested RAM |
|-----------|----------------|
| `universal-model-explainability` | 1–2 GB |
| `flexible-data-interpretability` | 1 GB |
| `kafka-xai-consumer` | 2–4 GB (model load + SHAP) |

## Topic names (align with AutoDW / Agentic Core)

| Topic | Direction |
|-------|-----------|
| `xai-trigger-events` | Agentic Core → XAI consumer |
| `xai-complete-events` | XAI → orchestrator (if consumer publishes) |
| DW emits `xai-events` / completion via API when report saved | XAI → AutoDW API |

Confirm exact topic names in the XAI consumer source — update `.env.example` if your repo uses different names.
