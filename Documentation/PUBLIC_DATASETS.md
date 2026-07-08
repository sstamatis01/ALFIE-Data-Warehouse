# Public Datasets (Summer School Catalog)

This document describes how AutoDW supports a **public dataset catalog** stored in MinIO + MongoDB, so that the frontend UI and Agentic Core can offer “starter datasets” for the summer school.

## Goals

- Store ~12 datasets once in a shared (public) space.
- Let users **browse** public datasets and **import** one into their own workspace.
- Keep the rest of the ML/Kafka flow unchanged (bias → AutoML → XAI → drift).

## Data model

Public datasets are stored in the same MongoDB collection (`datasets`) but are marked with:

- `is_public=true`
- `user_id="public"` (reserved system owner)

User imports from the catalog store a **reference** instead of duplicating storage:

- `is_public=false`
- `public_link={ "dataset_id": "<public id>", "version": "<public version>" }`

The storage layout in MinIO remains the standard layout, just under a reserved owner:

- `datasets/public/{dataset_id}/{version}/...`

## API endpoints

### List public datasets

- `GET /datasets/public?skip=0&limit=100&q=<optional>&tags=tag1,tag2` — all public versions (v1, v2, …)

### List public datasets for UI browse (v1 only)

- `GET /datasets/public/catalog?skip=0&limit=100&q=<optional>&tags=tag1,tag2` — **one row per dataset** (original **v1** only; no split v2 rows)

Use this endpoint in the frontend catalog so users do not see the same dataset twice. Selection/import via `POST /datasets/public/{id}/import/{user_id}` is unchanged (user still gets v1+v2 links when a split exists).

### Get a public dataset (latest)

- `GET /datasets/public/{dataset_id}`

### Get a public dataset version

- `GET /datasets/public/{dataset_id}/version/{version}`

### Upload into the public catalog (admin/ops)

- `POST /datasets/public/upload` (multipart form: `file`, optional `dataset_id`, `name`, `description`, `tags`, `public_source`)

Important: this endpoint **does not emit Kafka** `dataset-events`. The pipeline should only start after a user imports a dataset.

### Import a public dataset into a user workspace

- `POST /datasets/public/{public_dataset_id}/import/{user_id}?public_version=<optional>&dataset_id=<optional>`

This creates **user-scoped metadata** that references the public MinIO objects (no server-side copy):

- `public_link`: `{ "dataset_id": "<public id>", "version": "<public version>" }`
- `file_path` / `files[].file_path` use the user namespace layout for API consistency
- Downloads resolve `public_link` server-side to `datasets/public/{id}/{version}/...`

After import, AutoDW emits **Kafka `dataset-events`** (unchanged schema) for the imported version so the normal pipeline can proceed. Consumers should fetch bytes via the existing download endpoints using the user's `user_id` and `dataset_id`.

**Restrictions for linked imports:**

- `PUT /datasets/{user_id}/{dataset_id}` returns **403** (metadata edits are not allowed)
- `DELETE` removes only the user's metadata; **public catalog objects are never deleted**

## Ingesting the summer school datasets

Use the helper:

```bash
python scripts/ingest_public_datasets.py --api-base http://localhost:8000 --dir ./summer_school_datasets
```

Notes:

- The script uploads every matching file under the directory (recursive).
- Extensions can be controlled with repeated `--ext` flags.
- By default it uploads common tabular extensions (`.csv`, `.xls`, `.xlsx`, `.json`, `.parquet`, `.tsv`, `.zip`, …).

