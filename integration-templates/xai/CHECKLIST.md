# XAI repo prep checklist (before GitLab push)

## 1. Repository layout (target)

```text
<xai-repo>/
  Dockerfile.xai-services          # or Dockerfile
  flexible-scripts/
  scripts/kafka_call.py            # or kafka_xai_consumer_example_v2.py
  requirements.txt
  xai/                             # ← copy integration-templates/xai/ here
    .env.example
    docker-compose.yaml
    README.md
  .github/workflows/
    docker-build-push.yml          # ← copy from .github-workflows-...example
  .dockerignore
```

## 2. Dockerfile / image

- [ ] Single image builds all three runtime roles (Flask + consumer)
- [ ] No hardcoded `alfie.iti.gr` in ENV or scripts
- [ ] `curl` available in image if healthchecks use it (or change healthcheck)
- [ ] All Python deps in `requirements.txt` (shap, matplotlib, joblib, aiokafka, …)

## 3. docker-compose.yaml (integration)

Include **only XAI services** (not Mongo/Kafka/AutoDW):

- [ ] `universal-model-explainability` → port **5010**
- [ ] `flexible-data-interpretability` → port **5001**
- [ ] `kafka-xai-consumer` → no host port; depends on both Flask services healthy
- [ ] Image: `gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:${XAI_VERSION}`
- [ ] `API_BASE` → AutoDW (`host.docker.internal:8000` for local test)
- [ ] `KAFKA_BOOTSTRAP_SERVERS` → `host.docker.internal:9092` (local test)
- [ ] `extra_hosts: host.docker.internal:host-gateway` (Linux)

## 4. README (partner-facing)

Must explain:

- [ ] Image URL and MODULE name `xai`
- [ ] Dependency on AutoDW (API + Kafka)
- [ ] `docker login` + `compose pull/up`
- [ ] Ports 5010 / 5001
- [ ] Topic `xai-trigger-events`
- [ ] RAM / disk notes
- [ ] How to test with AutoDW `1.0.0` stack running

## 5. Registry push

```bash
docker build -f Dockerfile.xai-services -t gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:1.0.0 .
docker push gitlab.catalink.eu:5050/external/alfie_eu/alfie/xai:1.0.0
```

## 6. Local test order

1. Start AutoDW: `autodw/docker-compose.yaml` (from Data Warehouse repo)
2. Start XAI: `xai/docker-compose.yaml` (from XAI repo)
3. Trigger `xai-trigger-events` or full pipeline via Agentic Core
4. Verify report in AutoDW / Kafka completion topic

## 7. Message to ALFIE team

Same format as AutoDW:

- Module: `xai`
- Image: `.../alfie/xai:1.0.0`
- Attach: `docker-compose.yaml`, `.env.example`, README

## 8. Parallel Kafka consumers (optional)

- [ ] AutoDW API includes `POST /jobs/xai/claim` (Data Warehouse repo)
- [ ] Consumer sends `job_key` (or `report_type` + `level` so API builds it); skip on HTTP 409
- [ ] `docker-compose.replicas.yaml` — 3× `kafka-xai-consumer-*`, same `KAFKA_CONSUMER_GROUP`
- [ ] Topic `xai-trigger-events` has ≥3 partitions
- [ ] Flask explainability services remain single-instance (consumer only scales)
