# Bundled static documents

Project reference PDFs baked into the `autodw` Docker image and served by the API for localhost and partner integrations.

## Files

| ID | File | Purpose |
|----|------|---------|
| `altai` | `altai.pdf` | Assessment List for Trustworthy AI (ALTAI) |
| `ai-ethics` | `ai-ethics.pdf` | Ethics by Design and Ethics of Use for AI |

`manifest.json` maps stable IDs → filenames/titles. Prefer IDs in client code, not filenames.

## API (other services)

```text
GET /static-docs
GET /static-docs/{doc_id}
GET /static-docs/{doc_id}/download
```

Examples:

```bash
# Catalog
curl -s http://localhost:8000/static-docs

# Download
curl -o altai.pdf http://localhost:8000/static-docs/altai/download
curl -o ai-ethics.pdf http://localhost:8000/static-docs/ai-ethics/download
```

From another container on the AutoDW network:

```text
http://api:8000/static-docs/altai/download
```

Behind the ITI reverse proxy:

```text
https://alfie.iti.gr/autodw/static-docs/altai/download
```

## Image build

The Dockerfile copies this folder to `/app/static_docs/`. After tagging a release (e.g. `v1.0.5`), the registry image includes these PDFs.

Override path at runtime if needed:

```env
STATIC_DOCS_DIR=/app/static_docs
```

## Updating a document

1. Replace the PDF under `static_docs/` (keep the same filename, or update `manifest.json`).
2. Rebuild and push the `autodw` image.
