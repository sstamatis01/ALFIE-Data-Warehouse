# AutoDW (Data Warehouse API) – Capabilities Overview

This document summarizes the capabilities of the **AutoDW** (Automated Data Warehouse) API as of the latest updates. Use it as a high-level reference for what the system supports.

---

## Table of Contents

1. [Core Data & Storage](#core-data--storage)
2. [ML Pipeline & Kafka Orchestration](#ml-pipeline--kafka-orchestration)
3. [Concept Drift & 70-15-15 Split](#concept-drift--70-15-15-split)
4. [AI Models & XAI Reports](#ai-models--xai-reports)
5. [ETD-Hub & GraphDB](#etd-hub--graphdb)
6. [User Files (Chatbot Attachments)](#user-files-chatbot-attachments)
7. [Deployment & Integration](#deployment--integration)

---

## Core Data & Storage

| Capability | Description |
|------------|-------------|
| **Datasets** | Upload single files or folders (ZIP). Metadata in MongoDB, files in MinIO. User-scoped with versioning (v1, v2, …). |
| **Versioning** | Each upload can create a new version; v1 is always the original; v2 can hold the automatic train/test/drift split when applicable. |
| **Folder upload** | Upload a ZIP; contents are extracted and stored under `datasets/{user_id}/{dataset_id}/{version}/`. Optional structure preservation. |
| **Download** | Download by user/dataset/version; optional `?split=train|test|drift` to get only that subset when a split exists. |
| **Search** | Search datasets by query, tags, file type. |
| **MinIO** | S3-compatible object storage; single bucket with organized paths (datasets, models, xai_reports, user-files). |
| **MongoDB** | Metadata, users, configs, reports; indexes for performance. |

---

## ML Pipeline & Kafka Orchestration

The Data Warehouse participates in an event-driven ML pipeline via Kafka:

| Topic | Produced by | Consumed by | Purpose |
|-------|-------------|-------------|---------|
| `dataset-events` | DW API | Agentic Core | Dataset uploaded (v2 when split exists) |
| `bias-trigger-events` | Agentic Core | Bias Detector | Trigger bias detection |
| `bias-events` | DW API | Agentic Core | Bias report saved |
| `automl-trigger-events` | Agentic Core | AutoML Consumer | Trigger model training |
| `automl-events` | DW API | Agentic Core | Model uploaded |
| `xai-trigger-events` | Agentic Core | XAI Consumer | Trigger XAI report generation |
| `xai-events` | DW API | Agentic Core | XAI report saved |
| `concept-drift-trigger-events` | Agentic Core / orchestration | Concept Drift Consumer | Trigger drift detection & retrain |
| `concept-drift-complete-events` | Concept Drift Consumer | Orchestration | Drift run complete, new model version |

**Flow (simplified):** Dataset upload → Bias detection → AutoML training → Model upload → XAI report generation. Concept drift runs after AutoML using the **drift** split (15%) and can upload a new model version.

See [KAFKA_ORCHESTRATION_COMPLETE.md](KAFKA_ORCHESTRATION_COMPLETE.md) and [KAFKA_QUICK_REFERENCE.md](KAFKA_QUICK_REFERENCE.md).

---

## Concept Drift & 70-15-15 Split

- **Automatic split:** For suitable tabular datasets (CSV, Excel), the DW can automatically create a **70% train / 15% test / 15% drift** split when:
  - The file (or folder) is large enough: `num_samples > (num_features + 1) * 10`
  - A second version is requested (e.g. v2) via `version_split`.
- **Where it’s stored:** Original always in v1; split stored under v2 in MinIO as `train/`, `test/`, `drift/` subfolders.
- **Kafka:** The DW emits `dataset-events` for the **v2** (split) version so the pipeline (bias, AutoML, XAI) runs on the split data.
- **Concept drift consumer:** Uses only the **drift** split: `GET .../download?split=drift`. It runs ADWIN, retrains with AutoGluon, and uploads a new model version to the DW.

See [CONCEPT_DRIFT_KAFKA.md](CONCEPT_DRIFT_KAFKA.md).

---

## AI Models & XAI Reports

| Capability | Description |
|------------|-------------|
| **AI Models** | Upload single model file or folder (ZIP). Stored in MinIO under `models/{user_id}/{model_id}/{version}/`. Metadata in MongoDB; tagging and search. |
| **Bias reports** | Stored per user/dataset; Kafka events when reports are saved. |
| **Transformation reports** | Metadata for data transformation pipelines. |
| **XAI reports** | HTML reports stored in MinIO; metadata in MongoDB. Upload triggers `xai-events`. Download via API. |

See [AI_MODELS_README.md](AI_MODELS_README.md), [XAI_REPORTS_README.md](XAI_REPORTS_README.md).

---

## ETD-Hub & GraphDB

### ETD-Hub

- **Purpose:** Reddit-like forum for ethical AI: themes (case studies), questions, answers, votes, experts.
- **API:** REST endpoints for themes, questions, answers, votes, experts; import/export (JSON, Excel).
- **Storage:** MongoDB collections; optional file attachments (documents) in the future.

See [ETD_HUB_README.md](ETD_HUB_README.md), [ETD_HUB_GRAPHDB_INTEGRATION.md](ETD_HUB_GRAPHDB_INTEGRATION.md).

### GraphDB

- **Purpose:** Manage SPARQL endpoints and run SELECT/UPDATE queries against GraphDB (or other SPARQL stores).
- **Configs:** Stored in MongoDB (not in GraphDB). Create configs via API with endpoint URLs, repository name, credentials.
- **Initialization from backup:** GraphDB can start with data from a backup (e.g. from another AutoDW instance). Place a `.tar.gz` of the GraphDB data in `graphdb_init/`; the Docker entrypoint restores it when the data volume is empty. **Configs are not in the backup**—create them via the API after first run.
- **Scripts:** `graphdb_init/README.md`, `graphdb_init/create_graphdb_config.sh`, `graphdb_etd_hub_kg_create_and_query.py` (create config + run SPARQL for e.g. `etd-hub-kg-test`).

See [GRAPHDB_README.md](GRAPHDB_README.md), [graphdb_init/README.md](../graphdb_init/README.md).

---

## User Files (Chatbot Attachments)

- **Purpose:** Simple upload/list/download/delete of files attached by users (e.g. for a chatbot UI). Files are stored in MinIO; metadata in MongoDB.
- **Allowed types:** `.txt`, `.md`, `.csv`, `.json`, `.xml`, `.pdf`, `.doc`, `.docx`, `.odt`, `.rtf`. Max size 20 MB per file.
- **Endpoints:**
  - `POST /user-files/upload/{user_id}` – Upload (multipart: file, optional name, description, project_id).
  - `GET /user-files/{user_id}` – List (query: project_id, skip, limit).
  - `GET /user-files/{user_id}/{file_id}` – Get metadata.
  - `GET /user-files/{user_id}/{file_id}/download` – Download file (for parsing, summarization, etc.).
  - `DELETE /user-files/{user_id}/{file_id}` – Delete file.
- **Storage path:** `user-files/{user_id}/{file_id}/{filename}` in MinIO. Each file gets a unique `file_id` (ObjectId).

See [USER_FILES_README.md](USER_FILES_README.md).

---

## Deployment & Integration

- **Docker Compose:** MongoDB, MinIO, Kafka (+ Zookeeper), GraphDB, DW API, optional consumers (bias, AutoML, concept-drift, etc.). See [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md).
- **GraphDB init:** Use `graphdb_init/` and a backup `.tar.gz` to seed GraphDB data; create configs via API.
- **Partners:** Integrate via DW API only; do not depend on direct MongoDB/MinIO access. See [SHARING_WITH_PARTNERS_README.md](SHARING_WITH_PARTNERS_README.md), [PARTNER_INTEGRATION_CHECKLIST.md](PARTNER_INTEGRATION_CHECKLIST.md).

---

## Quick Reference – Main Docs

| Topic | Document |
|-------|----------|
| **This overview** | [CAPABILITIES_OVERVIEW.md](CAPABILITIES_OVERVIEW.md) |
| **Doc index** | [INDEX.md](INDEX.md) |
| **Kafka flow** | [KAFKA_ORCHESTRATION_COMPLETE.md](KAFKA_ORCHESTRATION_COMPLETE.md) |
| **Concept drift & 70-15-15** | [CONCEPT_DRIFT_KAFKA.md](CONCEPT_DRIFT_KAFKA.md) |
| **GraphDB** | [GRAPHDB_README.md](GRAPHDB_README.md) |
| **GraphDB init from backup** | [graphdb_init/README.md](../graphdb_init/README.md) |
| **User files** | [USER_FILES_README.md](USER_FILES_README.md) |
| **Docker** | [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md) |

---

*Last updated: February 2025*
