# ETD-Hub MongoDB seed (Excel)

AutoDW can pre-populate ETD-Hub forum data in MongoDB from an Excel export (same format as `GET /etd-hub/export/excel`).

## Bundled seed file

| File | Purpose |
|------|---------|
| `etd_hub_seed.xlsx` | Default seed baked into the `autodw` Docker image |

Update the seed by exporting from production:

```bash
curl -o etd_hub_init/etd_hub_seed.xlsx \
  'https://alfie.iti.gr/autodw/etd-hub/export/excel'
```

Then rebuild and push the `autodw` image.

## Auto-seed on API startup

When the API starts (including the registry image):

1. If `ETD_HUB_AUTO_SEED` is not disabled (default: **on**)
2. And `etd_themes` is **empty**
3. It imports `etd_hub_seed.xlsx` from `/app/etd_hub_init/` (or `ETD_HUB_SEED_PATH`)

Disable for empty ETD-Hub:

```env
ETD_HUB_AUTO_SEED=false
```

## Manual import

**API:**

```bash
curl -X POST "http://localhost:8000/etd-hub/import/upload-excel?clear_existing=true" \
  -H "accept: application/json" \
  -F "file=@etd_hub_init/etd_hub_seed.xlsx"
```

**Script (repo root):**

```bash
python scripts/init_etd_hub_from_excel.py
python scripts/init_etd_hub_from_excel.py --file etd_hub_init/etd_hub_seed.xlsx --no-clear
```

## Local stack without rebuild

Mount a newer export over the image copy in `autodw/docker-compose.yaml` (api service already documents `../etd_hub_init` when enabled).
