# Dataset Upload Stuck on Loading – Troubleshooting

## Quick steps

### 1. Check API logs (do this first)

On the server where Docker runs:

```bash
docker logs data-warehouse-api --tail 100
```

- If you see the request (e.g. "Uploading dataset...") and then nothing, the hang is likely in MinIO, MongoDB, or metadata extraction.
- If you see no log line for the upload, the request may not be reaching the API (network/proxy/Swagger).

### 2. Restart the Data Warehouse API

Often enough a restart fixes transient issues (Kafka/MinIO/Mongo connections, memory):

```bash
docker-compose restart api
```

Wait ~15–20 seconds, then try the upload again from the Swagger UI:  
http://160.40.52.44:8000/docs#/datasets/upload_dataset_datasets_upload__user_id__post

### 3. Try with a small file

- Use a small CSV (e.g. a few KB, < 1000 rows).
- If the small file works, the problem is likely **file size or complexity** (see below).

### 4. Bypass Swagger – test with curl

If Swagger stays on “loading”, test the same endpoint with curl:

```bash
curl -X POST "http://160.40.52.44:8000/datasets/upload/YOUR_USER_ID" \
  -F "file=@/path/to/your/small_file.csv" \
  -F "dataset_id=test-upload" \
  -F "name=Test Upload"
```

- If **curl succeeds**: the backend is fine; the issue is with the Swagger UI (browser/network/CORS).
- If **curl also hangs**: the issue is in the API or its dependencies (see below).

### 5. If it still hangs – check dependencies

Restart the whole stack so API, MinIO, MongoDB, and Kafka all come up clean:

```bash
docker-compose restart api mongodb minio kafka
# or
docker-compose down
docker-compose up -d
```

Then check health:

```bash
docker-compose ps
docker logs data-warehouse-api --tail 50
```

## Why uploads can “stick”

1. **Swagger UI** – Multipart uploads from the browser can hang due to CORS, large payloads, or UI timeouts.
2. **Large CSV/Excel** – The API reads the whole file and runs `pd.read_csv()` / `pd.read_excel()` for metadata. Very large files can be slow and memory-heavy and look like “stuck”.
3. **MinIO** – Slow or failing connection to MinIO can block the request.
4. **Kafka** – Sending the “dataset uploaded” event can block if Kafka is slow (event is sent after upload; usually not the main cause of “stuck”).
5. **Network** – Proxy/load balancer/firewall timeouts between you and `160.40.52.44:8000`.

## Summary

- **First:** Check `docker logs data-warehouse-api`, then **restart the API** and try again.
- **Then:** Try a **small file** and/or **curl** to see if the backend responds.
- **If still stuck:** Restart the full stack and re-check logs.
