# Dataset Folder Upload Feature

## Overview

The Data Warehouse now supports uploading multiple files as a dataset folder (ZIP archive), similar to how AI models support folder uploads. This allows users to organize related files together as a single dataset.

---

## 📊 Two Upload Methods

### 1. Single File Upload (Existing)
- **Endpoint**: `POST /datasets/upload/{user_id}`
- **File Type**: Single CSV, Excel, JSON, image, video, etc.
- **Metadata**: Full automatic extraction (columns, rows, data types)
- **Use Case**: Single tabular file or simple uploads

### 2. Folder Upload (New) ✨
- **Endpoint**: `POST /datasets/upload/folder/{user_id}`
- **File Type**: ZIP archive containing multiple files
- **Response**: **202 Accepted** + `UploadJobResponse` (`job_id`, `dataset_id`, `status: queued`)
- **Metadata**: Available **after the job completes** (file list; for vision, annotation columns too)
- **Use Case**: Multiple related files, vision image ZIPs, complex datasets

---

## Async job visibility (uploading vs missing)

Folder ZIP ingest is asynchronous. Until the job finishes, `GET /datasets/{user}/{dataset_id}` has no catalog row.

| Situation | HTTP | Meaning |
|-----------|------|---------|
| Job still `queued` / `running` | **409** `DATASET_UPLOAD_IN_PROGRESS` (body includes `job_id`, `progress`) | Wait / poll job — not deleted |
| Wrong id / deleted / never uploaded | **404** | Truly missing |
| Job `completed` | **200** `DatasetResponse` | Ready for Core / AutoML |

**Poll / rediscover jobs:**

- `GET /datasets/upload/jobs/{job_id}` — status of one job
- `GET /datasets/upload/jobs/{job_id}/dataset` — final metadata when completed (409 if still running)
- `GET /datasets/upload/jobs?user_id=...&dataset_id=...&status=queued,running` — resolve by dataset id
- `GET /datasets/{user_id}/upload/jobs?status=queued,running` — list active jobs (Dashboard refresh recovery)

**Dashboard contract:** return agent action immediately with `job_id`; poll until completed; then `refresh_state`. Do not put incomplete datasets into Agentic Core / AutoML triggers. In-progress uploads do **not** appear in `GET /datasets/{user_id}`.

**Vision annotation metadata (after job completes):** `columns`, `row_count`, `data_types` from the annotation CSV/JSON, plus `custom_metadata.modality=vision`, `annotation_file`, `filename_column`, `label_column`.

---

## 🚀 How It Works

### Folder Upload Process

1. **Create ZIP Archive** - Package your files into a ZIP
2. **Upload via API** - Send ZIP to the folder upload endpoint → **202** + `job_id`
3. **Background ingest** - Stage ZIP, extract, validate (vision annotations), upload to MinIO
4. **Metadata** - Written when the job completes (vision: annotation columns included)
5. **Version Management** - Auto-increments version (v1, v2, v3)
6. **Poll** - Client polls job until `completed`, then reads dataset metadata

### Metadata Differences

**Single File Upload:**
```json
{
  "is_folder": false,
  "file_type": "csv",
  "file_size": 1024,
  "columns": ["col1", "col2", "col3"],
  "row_count": 100,
  "data_types": {"col1": "int64", "col2": "string"},
  "files": null
}
```

**Folder Upload (non-vision):**
```json
{
  "is_folder": true,
  "file_type": "csv, json, txt",
  "file_size": 5120,
  "columns": null,
  "row_count": null,
  "data_types": null,
  "files": [ "... file list ..." ]
}
```

**Folder Upload (vision, after job completes):**
```json
{
  "is_folder": true,
  "columns": ["filename", "label"],
  "row_count": 1200,
  "data_types": {"filename": "object", "label": "object"},
  "custom_metadata": {
    "modality": "vision",
    "annotation_file": "annotations.csv",
    "filename_column": "filename",
    "label_column": "label",
    "file_count": 1201
  },
  "files": [ "... images + annotations ..." ]
}
```

---

## 📝 API Documentation

### Upload Folder Endpoint

**Endpoint**: `POST /datasets/upload/folder/{user_id}`

**Path Parameters:**
- `user_id` (string, required) - User identifier

**Form Data:**
- `zip_file` (file, required) - ZIP archive containing dataset files
- `dataset_id` (string, required) - Dataset identifier
- `name` (string, required) - Dataset name
- `description` (string, optional) - Dataset description
- `preserve_structure` (boolean, optional, default=true) - Preserve folder structure
- `tags` (string, optional) - Comma-separated tags

**Response:**
```json
{
  "dataset_id": "multi-file-dataset",
  "user_id": "user123",
  "name": "Complex Dataset",
  "version": "v1",
  "is_folder": true,
  "file_type": "csv, json, txt",
  "file_size": 5120,
  "original_filename": "dataset.zip",
  "files": [
    {
      "filename": "data1.csv",
      "file_path": "datasets/user123/multi-file-dataset/v1/data1.csv",
      "file_size": 2048,
      "file_type": "csv",
      "file_hash": "abc123..."
    },
    {
      "filename": "data2.csv",
      "file_path": "datasets/user123/multi-file-dataset/v1/data2.csv",
      "file_size": 2048,
      "file_type": "csv",
      "file_hash": "def456..."
    },
    {
      "filename": "metadata.json",
      "file_path": "datasets/user123/multi-file-dataset/v1/metadata.json",
      "file_size": 512,
      "file_type": "json",
      "file_hash": "ghi789..."
    }
  ],
  "columns": null,
  "row_count": null,
  "data_types": null,
  "tags": ["multi-file", "complex"],
  "custom_metadata": {
    "file_count": 3,
    "preserve_structure": true
  },
  "created_at": "2025-10-10T12:00:00",
  "updated_at": "2025-10-10T12:00:00"
}
```

---

## 💻 Usage Examples

### Using cURL

```bash
# Create a ZIP file first
zip -r dataset.zip data1.csv data2.csv metadata.json

# Upload the folder
curl -X POST "http://localhost:8000/datasets/upload/folder/user123" \
  -F "zip_file=@dataset.zip" \
  -F "dataset_id=my-complex-dataset" \
  -F "name=My Complex Dataset" \
  -F "description=Multiple related files" \
  -F "preserve_structure=true" \
  -F "tags=multi-file,experiment-01"
```

### Using Python

```python
import requests
import zipfile
import os

# Create ZIP archive
with zipfile.ZipFile('dataset.zip', 'w') as zipf:
    zipf.write('data1.csv')
    zipf.write('data2.csv')
    zipf.write('metadata.json')

# Upload folder
with open('dataset.zip', 'rb') as f:
    files = {'zip_file': ('dataset.zip', f, 'application/zip')}
    data = {
        'dataset_id': 'my-complex-dataset',
        'name': 'My Complex Dataset',
        'description': 'Multiple related files',
        'preserve_structure': 'true',
        'tags': 'multi-file,experiment-01'
    }
    
    response = requests.post(
        'http://localhost:8000/datasets/upload/folder/user123',
        files=files,
        data=data
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Uploaded {result['custom_metadata']['file_count']} files")
        print(f"   Version: {result['version']}")
        print(f"   Total size: {result['file_size']} bytes")
    else:
        print(f"❌ Error: {response.json()}")
```

---

## 🎯 Use Cases

### 1. Multi-File Datasets
```
dataset.zip
├── train.csv
├── test.csv
├── validation.csv
└── metadata.json
```

### 2. Time-Series Data
```
sensor_data.zip
├── 2024-01/
│   ├── day01.csv
│   ├── day02.csv
│   └── day03.csv
└── 2024-02/
    ├── day01.csv
    └── day02.csv
```

### 3. Multi-Modal Datasets
```
dataset.zip
├── images/
│   ├── image1.jpg
│   ├── image2.jpg
│   └── image3.jpg
├── annotations.json
└── metadata.csv
```

### 4. ML Pipeline Artifacts
```
experiment.zip
├── raw_data.csv
├── processed_data.csv
├── features.csv
└── config.yaml
```

---

## 🔍 Key Features

### ✅ Automatic Version Management
- First upload: `v1`
- Second upload: `v2`
- No manual version tracking needed

### ✅ Preserve Folder Structure
```
# With preserve_structure=true
datasets/user123/dataset1/v1/folder1/subfolder/file.csv

# With preserve_structure=false
datasets/user123/dataset1/v1/file.csv
```

### ✅ Simplified Metadata
- **No column analysis** - Faster processing
- **No row counting** - Avoids loading large files
- **Just file inventory** - Names, sizes, types, hashes

### ✅ Kafka Events
- Folder uploads trigger same `dataset-events` as single files
- Compatible with existing pipeline (bias detection, AutoML, XAI)

### ✅ File Filtering
- Skips hidden files (`.DS_Store`, etc.)
- Skips `__MACOSX` folders
- Only processes actual data files

---

## ⚙️ Technical Details

### Supported File Types
- **No restrictions** - Any file type can be included
- Common types: CSV, JSON, Excel, TXT, images, videos, etc.

### Size Limits
- Individual file: Depends on MinIO configuration
- ZIP archive: Depends on upload limits
- Recommended: < 1GB per ZIP

### Storage Structure
```
MinIO:
  datasets/
    {user_id}/
      {dataset_id}/
        {version}/
          file1.csv
          file2.json
          folder/
            file3.txt

MongoDB:
  datasets collection:
    {
      dataset_id: "...",
      version: "v1",
      is_folder: true,
      files: [
        {filename, file_path, size, type, hash},
        ...
      ]
    }
```

---

## 🔄 Comparison: Single vs Folder Upload

| Feature | Single File | Folder (ZIP) |
|---------|-------------|--------------|
| **Endpoint** | `/upload/{user_id}` | `/upload/folder/{user_id}` |
| **Input** | Single file | ZIP archive |
| **Metadata** | Full (columns, rows, types) | Simplified (file list only) |
| **Processing** | Reads and analyzes file | Extracts and inventories |
| **Use Case** | Single tabular data | Multiple/related files |
| **Speed** | Slower (analysis) | Faster (no analysis) |
| **Kafka Events** | ✅ Yes | ✅ Yes |
| **Auto-versioning** | ✅ Yes | ✅ Yes |

---

## 📋 Best Practices

### 1. Organize Files Logically
```
✅ Good:
dataset.zip
├── data/
│   ├── train.csv
│   └── test.csv
└── metadata.json

❌ Bad:
dataset.zip
├── file1.csv
├── copy_of_file1.csv
├── file1_backup.csv
└── temp.txt
```

### 2. Include Metadata File
```json
// metadata.json
{
  "description": "Experiment 01 results",
  "date": "2025-10-10",
  "files": {
    "train.csv": "Training data",
    "test.csv": "Test data"
  }
}
```

### 3. Use Meaningful Names
```
✅ experiment-2025-01-15.zip
✅ sensor-data-batch-03.zip
❌ data.zip
❌ temp.zip
```

### 4. Don't Include Unnecessary Files
- Remove system files (`.DS_Store`, `Thumbs.db`)
- Remove temporary files
- Remove backups or duplicates

---

## 🐛 Troubleshooting

### Error: "File must be a ZIP archive"
**Cause**: Uploaded file is not a ZIP  
**Solution**: Create a proper ZIP file

### Error: "No valid files found in ZIP"
**Cause**: ZIP is empty or contains only hidden files  
**Solution**: Verify ZIP contents

### Error: "Folder upload failed"
**Cause**: MinIO or extraction error  
**Solution**: Check logs, verify file permissions

### Files have wrong structure
**Cause**: `preserve_structure` setting  
**Solution**: Toggle `preserve_structure` parameter

---

## 🎉 Summary

✅ Upload multiple files as ZIP archives  
✅ Automatic extraction and storage  
✅ Simplified metadata (no content analysis)  
✅ Preserve or flatten folder structure  
✅ Auto-versioning like single files  
✅ Kafka events for pipeline integration  
✅ Same API patterns as AI models  

The folder upload feature makes it easy to work with complex, multi-file datasets while maintaining compatibility with existing workflows!

