# AutoML Predictor ZIP File Setup

## Issue

The `automl-consumer` service needs `automl_predictor.zip` to upload models to the Data Warehouse. This file must be available in the Docker container.

## Solution Options

### Option 1: Volume Mount (Recommended - No Rebuild Needed)

**Step 1:** Ensure `automl_predictor.zip` exists in the project root directory:
```bash
ls -la automl_predictor.zip
```

**Step 2:** The docker-compose.yml already has the volume mount configured:
```yaml
volumes:
  - ./automl_predictor.zip:/app/automl_predictor.zip:ro
```

**Step 3:** Restart the service:
```bash
docker-compose restart automl-consumer
```

**Pros:**
- No need to rebuild the Docker image
- Easy to update the file (just replace it and restart)

**Cons:**
- File must exist on the host machine
- If file doesn't exist, Docker will create an empty mount point (which will fail)

### Option 2: Include in Docker Image (Recommended for Production)

**Step 1:** Place `automl_predictor.zip` in the project root directory

**Step 2:** Update Dockerfile (uncomment the COPY line):
```dockerfile
COPY automl_predictor.zip ./automl_predictor.zip
```

**Step 3:** Rebuild the image:
```bash
docker-compose build automl-consumer
docker-compose up -d automl-consumer
```

**Pros:**
- File is part of the image (self-contained)
- No dependency on host file system
- Better for production deployments

**Cons:**
- Requires rebuild to update the file

### Option 3: Create a Dummy File (For Testing)

If you don't have the actual model file yet, you can create a dummy ZIP for testing:

```bash
# Create a simple dummy ZIP file
echo "dummy model content" > dummy_model.txt
zip automl_predictor.zip dummy_model.txt
rm dummy_model.txt
```

## Verification

After setup, check the logs:
```bash
docker-compose logs automl-consumer | grep -i "model file"
```

You should see:
```
✅ Model file found: automl_predictor.zip (XXXX bytes)
```

Instead of:
```
⚠️  Model file not found: automl_predictor.zip
```

## Current Configuration

The docker-compose.yml is configured to use **Option 1 (Volume Mount)**. This means:

1. ✅ The file will be mounted from the host
2. ⚠️  The file **must exist** in the project root directory
3. ✅ No rebuild needed when updating the file

## Troubleshooting

### File Not Found Error

**Check if file exists:**
```bash
ls -la automl_predictor.zip
```

**Check if file is mounted in container:**
```bash
docker exec data-warehouse-automl-consumer ls -la /app/automl_predictor.zip
```

**If file doesn't exist, create it or use Option 2 (include in image)**

### Permission Issues

If you get permission errors:
```bash
chmod 644 automl_predictor.zip
```

### File Size Issues

Check file size:
```bash
ls -lh automl_predictor.zip
```

If the file is very large (>100MB), consider:
- Using Option 2 (include in image) for better performance
- Or ensuring the file is optimized/compressed
