# AutoML Consumer V2 - Real Model Folder Upload

## Overview

Version 2 of the AutoML consumer demonstrates uploading a real model with multiple files (model folder) to the Data Warehouse. This uses your actual `xai-model/model-explanation-endpoint` folder.

---

## 🎯 Differences: V1 vs V2

### V1 (kafka_automl_consumer_example.py)
- ✅ Uses dummy `model.pkl` file
- ✅ Uploads single file: `/upload/single/{user_id}`
- ✅ Good for basic testing

### V2 (kafka_automl_consumer_example_v2.py) ✨
- ✅ Uses real model from `xai-model/model-explanation-endpoint/`
- ✅ Uploads folder with multiple files: `/upload/folder/{user_id}`
- ✅ Tests complete real-world scenario
- ✅ Model contains: `model.pkl` + `label_encoders.pkl`

---

## 📦 Model Folder Structure

```
xai-model/
└── model-explanation-endpoint/
    ├── model.pkl              # Main model file
    └── label_encoders.pkl     # Label encoders
```

---

## 🚀 How It Works

### Process Flow

1. **Receives AutoML trigger event** from Agentic Core
2. **Downloads dataset** (single file or folder)
3. **Loads and analyzes** dataset
4. **Creates ZIP** from `xai-model/model-explanation-endpoint/`
5. **Uploads model folder** to DW using `/upload/folder/{user_id}`
6. **DW extracts** and stores all model files
7. **DW produces** automl-events
8. **Pipeline continues** to XAI stage

### Key Features

- ✅ **Real model files** - Uses actual trained model
- ✅ **Multiple files** - Tests folder upload
- ✅ **Auto-cleanup** - Removes temp ZIP after upload
- ✅ **Error handling** - Robust error handling
- ✅ **Detailed logging** - Shows all files being uploaded

---

## 💻 Usage

### Start V2 Consumer

```bash
# Use different consumer group to run alongside V1
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
KAFKA_AUTOML_TRIGGER_TOPIC=automl-trigger-events \
KAFKA_CONSUMER_GROUP=automl-consumer-v2 \
python kafka_automl_consumer_example_v2.py
```

**On startup, you'll see:**
```
================================================================================
📦 Model Files to Upload:
================================================================================
  ✅ model.pkl (XXX bytes)
  ✅ label_encoders.pkl (XXX bytes)
================================================================================

Starting AutoML Trigger consumer V2 (Real Model Folder)
================================================================================
Model folder: xai-model/model-explanation-endpoint
Waiting for AutoML trigger events from Agentic Core...
```

### When Processing Event

```
================================================================================
AutoML Trigger Message received (V2)
  Event=...
================================================================================
Processing AutoML trigger for dataset dataset123
  User: user123
  Target column: target
  Task type: classification
  Dataset type: FOLDER
  File count: 3
Dataset downloaded: 5120 bytes
Extracting folder dataset...
Extracted 3 files
================================================================================
TRAINING MODEL (V2 - Real Model Folder)
  Target: target
  Task: classification
  Data shape: (100, 5)
================================================================================
Using real model from: xai-model/model-explanation-endpoint
  - model.pkl (XXX bytes)
  - label_encoders.pkl (XXX bytes)
Added to ZIP: model.pkl
Added to ZIP: label_encoders.pkl
Created ZIP: temp_model_automl_dataset123_1728561234.zip
Uploading model folder to DW: automl_dataset123_1728561234
================================================================================
✅ MODEL FOLDER UPLOADED TO DW!
   Model ID: automl_dataset123_1728561234
   Version: v1
   Files: 2
   Total size: 0.XX MB
================================================================================
AutoML event will be automatically sent by the DW
Cleaned up temp ZIP: temp_model_automl_dataset123_1728561234.zip
AutoML V2 processing completed for dataset dataset123
```

---

## 🧪 Testing

### Complete Flow Test

```bash
# Terminal 1: DW API
python run.py

# Terminal 2: Agentic Core
python kafka_agentic_core_consumer_example.py

# Terminal 3: Bias Detector
python kafka_bias_detector_consumer_example.py

# Terminal 4: AutoML V2 (not V1!)
python kafka_automl_consumer_example_v2.py

# Terminal 5: XAI Consumer
python kafka_xai_consumer_example.py

# Terminal 6: Upload dataset
curl -X POST "http://localhost:8000/datasets/upload/testuser" \
  -F "file=@heart_rate.csv" \
  -F "dataset_id=v2-test" \
  -F "name=V2 Test"
```

### Verify Model Upload

```bash
# Get model metadata
curl "http://localhost:8000/ai-models/testuser/automl_v2-test_XXXXX" | jq

# List model files
curl "http://localhost:8000/ai-models/testuser/automl_v2-test_XXXXX/files" | jq

# Should show:
# [
#   {"filename": "model.pkl", "file_size": XXX, ...},
#   {"filename": "label_encoders.pkl", "file_size": XXX, ...}
# ]
```

---

## 🔄 Run Both Versions Simultaneously

You can run both V1 and V2 consumers at the same time with different consumer groups:

```bash
# Terminal 1: V1 - Uses dummy model.pkl
KAFKA_CONSUMER_GROUP=automl-consumer-v1 \
python kafka_automl_consumer_example.py

# Terminal 2: V2 - Uses real model folder
KAFKA_CONSUMER_GROUP=automl-consumer-v2 \
python kafka_automl_consumer_example_v2.py
```

**Result**: Both consumers will receive the same AutoML trigger events and upload different models!

---

## 📊 What V2 Tests

- ✅ **Folder upload endpoint** - Tests `/upload/folder/{user_id}` for AI models
- ✅ **Multiple model files** - Tests models with dependencies (encoders, weights, etc.)
- ✅ **Real-world scenario** - Uses actual trained model
- ✅ **ZIP creation** - Tests dynamic ZIP creation from folder
- ✅ **Complete flow** - From trigger to upload to XAI
- ✅ **Auto-versioning** - Each upload creates new version
- ✅ **Cleanup** - Removes temp files

---

## 💡 Customization

### Use Different Model Folder

```python
# Change at top of file
MODEL_FOLDER_PATH = "path/to/your/model/folder"
```

### Add More Model Files

Just add files to the folder - they'll all be included:
```
xai-model/model-explanation-endpoint/
├── model.pkl
├── label_encoders.pkl
├── scaler.pkl              # ✅ Will be included
├── feature_names.json      # ✅ Will be included
└── config.yaml             # ✅ Will be included
```

### Modify Upload Metadata

```python
# In upload_model_folder_to_dw function
data = {
    'model_id': model_id,
    'name': 'Your Custom Name',
    'description': 'Your description',
    'framework': 'pytorch',  # Change framework
    'algorithm': 'ResNet50',  # Add algorithm
    'tags': 'production,v2',  # Add tags
    # ...
}
```

---

## 🎯 Use Cases

### 1. Test Real Model Upload
- Verify folder upload works with actual model files
- Test with your production model structure

### 2. Test Multiple Files
- Model with separate encoder/scaler files
- Model with config files
- Model with metadata files

### 3. Test XAI Integration
- Upload real model
- Trigger XAI explanations
- Generate reports for real model

### 4. Compare V1 vs V2
- Run both consumers
- See single file vs folder uploads
- Compare behavior in pipeline

---

## 📋 Checklist

Before running V2:

- [ ] `xai-model/model-explanation-endpoint/` folder exists
- [ ] Folder contains model files (`model.pkl`, `label_encoders.pkl`)
- [ ] All other consumers running
- [ ] DW API running
- [ ] Different consumer group used (`automl-consumer-v2`)

---

## 🔍 Expected Results

### In Console
```
✅ MODEL FOLDER UPLOADED TO DW!
   Model ID: automl_test_1728561234
   Version: v1
   Files: 2
   Total size: 0.05 MB
```

### In Data Warehouse

**Model metadata:**
```json
{
  "model_id": "automl_test_1728561234",
  "version": "v1",
  "files": [
    {
      "filename": "model.pkl",
      "file_path": "models/testuser/automl_test_1728561234/v1/model.pkl",
      "file_size": 45678,
      "is_primary": true
    },
    {
      "filename": "label_encoders.pkl",
      "file_path": "models/testuser/automl_test_1728561234/v1/label_encoders.pkl",
      "file_size": 12345,
      "is_primary": false
    }
  ]
}
```

### In Kafka
- `automl-events` message produced with model info
- Includes `is_folder` info from dataset
- XAI trigger follows

---

## 📁 Files

**New:**
- ✅ `kafka_automl_consumer_example_v2.py` - V2 consumer with folder upload

**Documentation:**
- ✅ `Documentation/AUTOML_CONSUMER_V2.md` - This guide

**Model Files (Your Existing):**
- ✅ `xai-model/model-explanation-endpoint/model.pkl`
- ✅ `xai-model/model-explanation-endpoint/label_encoders.pkl`

---

## ✅ Summary

**V2 Consumer Features:**
- ✅ Uses real model with multiple files
- ✅ Creates ZIP dynamically from folder
- ✅ Uploads via folder endpoint
- ✅ Tests complete real-world scenario
- ✅ Auto-cleanup of temp files
- ✅ Detailed logging

**Benefits:**
- Test with actual model structure
- Verify folder upload for models works
- Complete end-to-end test with real files
- Can run alongside V1 for comparison

Ready to test! 🚀

