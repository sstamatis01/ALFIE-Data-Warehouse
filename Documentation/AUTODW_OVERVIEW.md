# AutoDW (Data Warehouse) – Technical Overview

Concise technical overview of the AutoDW stack, services, API surface, and event flow as implemented.

---

## 1. Stack

| Component | Role | Port (host) |
|-----------|------|-------------|
| **MongoDB** | Metadata and application data | 27017 |
| **MinIO** | Object storage (datasets, models, reports, user files) | 9000 (API), 9001 (console) |
| **Zookeeper** | Kafka coordination | (internal) |
| **Kafka** | Event bus for orchestration | 9092 |
| **Kafka UI** | Optional UI for topics/consumers | 8080 |
| **GraphDB** | Semantic / RDF store (SPARQL) | 7200 |
| **DW API** | FastAPI application (all domains below) | 8000 |
| **bias-detector** | Kafka consumer: bias triggers → reports → Kafka | (no port) |
| **automl-consumer** | Kafka consumer: AutoML triggers → model upload + completion event | (no port) |

External orchestrators (e.g. Agentic Core) and XAI consumers run outside this stack and connect to Kafka and the API.

---

## 2. API Surface (Routers)

All under base URL `http://<host>:8000`. OpenAPI: `/docs`.

| Prefix | Purpose |
|--------|--------|
| `/datasets` | Upload (single/folder), list, get, search, download, delete; versioning per user/dataset. |
| `/users` | User management. |
| `/bias-reports` | Bias reports (create, get by user/dataset). |
| `/transformation-reports` | Transformation/mitigation reports. |
| `/ai-models` | AI model upload (single/folder), list, get, search, download, delete. |
| `/xai-reports` | XAI report upload, list, get, download. |
| `/etd-hub` | ETD-Hub (themes, questions, answers, experts, documents, votes); export. |
| `/etd-hub/import` | Bulk import ETD-Hub data (JSON). |
| `/graphdb` | GraphDB configs (CRUD), SPARQL execute/test. |
| `/user-files` | User project files (chatbot attachments): upload, list, get metadata, download, delete. |

Health: `GET /health`.

---

## 3. Storage Layout (MinIO)

Single bucket (`data-warehouse`). Path conventions:

| Path pattern | Content |
|--------------|---------|
| `datasets/{user_id}/{dataset_id}/{version}/` | Dataset files (CSV, Excel, etc.). |
| `ai-models/{user_id}/{model_id}/{version}/` | AI model files. |
| `xai-reports/` | XAI report artifacts. |
| `user-files/{user_id}/{file_id}/` | User project files (txt, pdf, doc, etc.). |

Metadata for datasets, models, reports, user files, ETD-Hub, GraphDB configs, etc. is in **MongoDB** (database: `data_warehouse`).

---

## 4. Kafka Topics and Flow

Topics used by the DW and its workers (config: `app/core/config.py`).

| Topic | Producer | Consumer(s) | When |
|-------|----------|------------|------|
| `dataset-events` | DW API | Agentic Core (external) | Dataset uploaded |
| `bias-detection-trigger-events` | Agentic Core | bias-detector (in stack) | Bias check requested |
| `bias-detection-complete-events` | DW API (on report save) | Agentic Core | Bias report saved |
| `automl-trigger-events` | Agentic Core | automl-consumer (in stack) | AutoML training requested |
| `automl-complete-events` | automl-consumer | Agentic Core | Model uploaded / completion signalled |
| `xai-trigger-events` | Agentic Core | XAI consumer (external) | XAI requested |
| `xai-complete-events` | DW API (on XAI upload) | Agentic Core | XAI report saved |

Flow in short: **Dataset upload** → **dataset-events** → Agentic Core → **bias-trigger** → bias-detector → report to DW → **bias-complete** → Agentic Core → **automl-trigger** → automl-consumer → model to DW + **automl-complete** → Agentic Core → **xai-trigger** → XAI consumer → report to DW → **xai-complete** → Agentic Core.

---

## 5. In-Stack Workers

- **bias-detector**  
  Script: `kafka_bias_detector_consumer_example.py`.  
  Consumes `bias-detection-trigger-events`, produces bias reports via DW API, which then emits `bias-detection-complete-events`.

- **automl-consumer**  
  Script: `kafka_automl_consumer_example.py`.  
  Consumes `automl-trigger-events`; validates dataset via API; uploads a fixed model file (`automl_predictor.zip`) to the DW; produces `automl-complete-events`. No external AutoML service; dummy implementation for the pipeline.

Agentic Core and XAI consumer are external; they use the same Kafka topics and DW API.

---

## 6. Main Capabilities (Summary)

- **Datasets**: Versioned upload (single/folder), metadata extraction, search, download, delete. Events on upload.
- **AI models**: Versioned upload (single/folder), link to training dataset, events on upload (and completion event when triggered by automl-consumer).
- **Bias & transformation**: Reports stored and linked to datasets; Kafka events for bias pipeline.
- **XAI reports**: Upload and serve; Kafka events for completion.
- **ETD-Hub**: Forum-like data (themes, questions, answers, experts, documents, votes); import/export.
- **GraphDB**: Store and manage SPARQL endpoint configs; run SELECT/UPDATE; test connections. GraphDB data lives in its own volume/instance; see GRAPHDB_MIGRATION.md for backup/restore.
- **User project files**: Simple upload/list/download/delete for user-supplied files (e.g. chatbot attachments); types such as txt, md, pdf, doc, docx; 20 MB limit.

---

## 7. Deployment (Docker)

- Compose file: `docker-compose.yml` (no `version`; Compose v2).
- API code is mounted from `./app`; restarting the `api` service is enough for code changes (no rebuild needed for app-only changes).
- Rebuild only when dependencies or Dockerfile change:  
  `docker compose up -d --build api` (or rebuild specific services).

Restart API only after doc/code updates:

```bash
docker compose restart api
```

---

## 8. Further Detail

- **Kafka flow and payloads**: [KAFKA_ORCHESTRATION_COMPLETE.md](KAFKA_ORCHESTRATION_COMPLETE.md), [KAFKA_QUICK_REFERENCE.md](KAFKA_QUICK_REFERENCE.md).
- **Deployment and networking**: [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md).
- **GraphDB backup/migration**: [GRAPHDB_MIGRATION.md](GRAPHDB_MIGRATION.md).
- **Partner integration**: [SHARING_WITH_PARTNERS_README.md](SHARING_WITH_PARTNERS_README.md), [PARTNER_INTEGRATION_CHECKLIST.md](PARTNER_INTEGRATION_CHECKLIST.md).
- **Full doc index**: [INDEX.md](INDEX.md).

---

*Last updated to match current implementation (API, Kafka topics, workers, user-files, GraphDB).*
