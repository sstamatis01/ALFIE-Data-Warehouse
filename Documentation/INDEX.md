# Data Warehouse Documentation Index

Welcome to the Data Warehouse documentation! This index will help you find the right documentation for your needs.

---

## 📚 Quick Navigation

### 🚀 Getting Started
- **[README.md](../README.md)** - Main project README (in root directory)
- **[CAPABILITIES_OVERVIEW.md](CAPABILITIES_OVERVIEW.md)** - **Summary of all AutoDW capabilities** (recommended entry point)
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - Kafka orchestration implementation overview

### 🏗️ Architecture & Orchestration
- **[KAFKA_ORCHESTRATION_COMPLETE.md](KAFKA_ORCHESTRATION_COMPLETE.md)** - Complete Kafka architecture and flow
- **[KAFKA_QUICK_REFERENCE.md](KAFKA_QUICK_REFERENCE.md)** - Quick reference for topics and payloads
- **[KAFKA_FOLDER_SUPPORT.md](KAFKA_FOLDER_SUPPORT.md)** - Kafka support for folder datasets
- **[FOLDER_INFO_IN_ALL_KAFKA_MESSAGES.md](FOLDER_INFO_IN_ALL_KAFKA_MESSAGES.md)** - Folder info in all messages
- **[MODEL_FOLDER_SUPPORT_KAFKA.md](MODEL_FOLDER_SUPPORT_KAFKA.md)** - Model folder support in Kafka

### 🔌 API Documentation
- **[API_CHANGES_USER_ID_AND_VERSIONING.md](API_CHANGES_USER_ID_AND_VERSIONING.md)** - API changes and auto-versioning
- **[AI_MODELS_README.md](AI_MODELS_README.md)** - AI Models API documentation
- **[XAI_REPORTS_README.md](XAI_REPORTS_README.md)** - XAI Reports API documentation
- **[USER_FILES_README.md](USER_FILES_README.md)** - **User-files API** (chatbot attachments: upload, list, download, delete)
- **[DATASET_FOLDER_UPLOAD.md](DATASET_FOLDER_UPLOAD.md)** - Dataset folder upload guide
- **[DATASET_DOWNLOAD_DELETE.md](DATASET_DOWNLOAD_DELETE.md)** - Download and delete operations
- **[DATASET_FOLDER_COMPLETE.md](DATASET_FOLDER_COMPLETE.md)** - Complete folder implementation
- **[GRAPHDB_README.md](GRAPHDB_README.md)** - GraphDB SPARQL configs & query API; **init from backup** (see also [graphdb_init/README.md](../graphdb_init/README.md))

### 🧪 Testing Guides
- **[TEST_COMPLETE_FLOW.md](TEST_COMPLETE_FLOW.md)** - Complete end-to-end testing guide
- **[TEST_NEW_API_ENDPOINTS.md](TEST_NEW_API_ENDPOINTS.md)** - Testing new API endpoints
- **[END_TO_END_TESTING_UPDATE.md](END_TO_END_TESTING_UPDATE.md)** - End-to-end testing updates
- **[AUTOML_CONSUMER_V2.md](AUTOML_CONSUMER_V2.md)** - AutoML consumer V2 with real model folder
- **[CONCEPT_DRIFT_KAFKA.md](CONCEPT_DRIFT_KAFKA.md)** - Concept drift events & **automatic 70-15-15 train/test/drift split**

### 🤝 Partner Integration
- **[SHARING_WITH_PARTNERS_README.md](SHARING_WITH_PARTNERS_README.md)** - Guide for sharing with partners
- **[DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md)** - Docker deployment and networking
- **[PARTNER_INTEGRATION_CHECKLIST.md](PARTNER_INTEGRATION_CHECKLIST.md)** - Integration checklist
- **[PARTNER_INTEGRATION_IMPROVEMENTS.md](PARTNER_INTEGRATION_IMPROVEMENTS.md)** - Partner integration improvements

### 🐛 Bug Fixes & Updates
- **[BUG_FIX_BIAS_EVENTS.md](BUG_FIX_BIAS_EVENTS.md)** - Bias events bug fix documentation
- **[CSV_ENCODING_FIX.md](CSV_ENCODING_FIX.md)** - CSV encoding error fix
- **[FOLDER_INFO_PARSING_FIX.md](FOLDER_INFO_PARSING_FIX.md)** - Folder info parsing location fix

### 📜 Historical/Reference
- **[KAFKA_AUTOML_IMPLEMENTATION.md](KAFKA_AUTOML_IMPLEMENTATION.md)** - AutoML Kafka implementation (outdated - see orchestration docs)

---

## 🎯 Documentation by Role

### For New Developers
1. Start with [README.md](../README.md)
2. Read **[CAPABILITIES_OVERVIEW.md](CAPABILITIES_OVERVIEW.md)** for a full capability summary
3. Read [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
4. Review [KAFKA_ORCHESTRATION_COMPLETE.md](KAFKA_ORCHESTRATION_COMPLETE.md)
5. Follow [TEST_COMPLETE_FLOW.md](TEST_COMPLETE_FLOW.md)

### For API Users
1. [API_CHANGES_USER_ID_AND_VERSIONING.md](API_CHANGES_USER_ID_AND_VERSIONING.md)
2. [AI_MODELS_README.md](AI_MODELS_README.md)
3. [XAI_REPORTS_README.md](XAI_REPORTS_README.md)
4. [USER_FILES_README.md](USER_FILES_README.md) - User-files (chatbot attachments)
5. [TEST_NEW_API_ENDPOINTS.md](TEST_NEW_API_ENDPOINTS.md)

### For Partners Integrating
1. [SHARING_WITH_PARTNERS_README.md](SHARING_WITH_PARTNERS_README.md) - Start here!
2. [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md)
3. [PARTNER_INTEGRATION_CHECKLIST.md](PARTNER_INTEGRATION_CHECKLIST.md)
4. [KAFKA_ORCHESTRATION_COMPLETE.md](KAFKA_ORCHESTRATION_COMPLETE.md)

### For Kafka Consumers
1. [KAFKA_ORCHESTRATION_COMPLETE.md](KAFKA_ORCHESTRATION_COMPLETE.md) - Complete architecture
2. [KAFKA_QUICK_REFERENCE.md](KAFKA_QUICK_REFERENCE.md) - Quick reference
3. Consumer example scripts (in root directory)

### For Testers
1. [TEST_COMPLETE_FLOW.md](TEST_COMPLETE_FLOW.md)
2. [TEST_NEW_API_ENDPOINTS.md](TEST_NEW_API_ENDPOINTS.md)
3. [END_TO_END_TESTING_UPDATE.md](END_TO_END_TESTING_UPDATE.md)

---

## 📂 File Organization

```
data-warehouse-app/
├── README.md                          # Main project README
├── Documentation/                     # All documentation (you are here!)
│   ├── INDEX.md                      # This file
│   ├── IMPLEMENTATION_SUMMARY.md     # Kafka implementation overview
│   ├── CAPABILITIES_OVERVIEW.md      # Summary of all AutoDW capabilities
│   ├── USER_FILES_README.md          # User-files API (chatbot attachments)
│   ├── GRAPHDB_README.md            # GraphDB + init from backup
│   ├── CONCEPT_DRIFT_KAFKA.md       # Concept drift & 70-15-15 split
│   ├── KAFKA_ORCHESTRATION_COMPLETE.md
│   ├── KAFKA_QUICK_REFERENCE.md
│   ├── API_CHANGES_USER_ID_AND_VERSIONING.md
│   ├── AI_MODELS_README.md
│   ├── XAI_REPORTS_README.md
│   ├── TEST_COMPLETE_FLOW.md
│   ├── TEST_NEW_API_ENDPOINTS.md
│   ├── END_TO_END_TESTING_UPDATE.md
│   ├── SHARING_WITH_PARTNERS_README.md
│   ├── DOCKER_DEPLOYMENT_GUIDE.md
│   ├── PARTNER_INTEGRATION_CHECKLIST.md
│   ├── PARTNER_INTEGRATION_IMPROVEMENTS.md
│   ├── BUG_FIX_BIAS_EVENTS.md
│   └── KAFKA_AUTOML_IMPLEMENTATION.md
├── kafka_*_consumer_example.py        # Consumer scripts
├── app/                               # Application code
└── ...
```

---

## 🔍 Find Documentation by Topic

### Kafka & Event-Driven Architecture
- [KAFKA_ORCHESTRATION_COMPLETE.md](KAFKA_ORCHESTRATION_COMPLETE.md) - Complete guide
- [KAFKA_QUICK_REFERENCE.md](KAFKA_QUICK_REFERENCE.md) - Quick reference
- [CONCEPT_DRIFT_KAFKA.md](CONCEPT_DRIFT_KAFKA.md) - Concept drift & 70-15-15 split
- [KAFKA_AUTOML_IMPLEMENTATION.md](KAFKA_AUTOML_IMPLEMENTATION.md) - Historical

### API Endpoints
- [API_CHANGES_USER_ID_AND_VERSIONING.md](API_CHANGES_USER_ID_AND_VERSIONING.md) - API changes
- [AI_MODELS_README.md](AI_MODELS_README.md) - AI models
- [XAI_REPORTS_README.md](XAI_REPORTS_README.md) - XAI reports
- [USER_FILES_README.md](USER_FILES_README.md) - User-files (chatbot attachments)
- [GRAPHDB_README.md](GRAPHDB_README.md) - GraphDB configs & SPARQL

### Docker & Deployment
- [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md) - Complete deployment guide

### Testing
- [TEST_COMPLETE_FLOW.md](TEST_COMPLETE_FLOW.md) - End-to-end testing
- [TEST_NEW_API_ENDPOINTS.md](TEST_NEW_API_ENDPOINTS.md) - API endpoint testing
- [END_TO_END_TESTING_UPDATE.md](END_TO_END_TESTING_UPDATE.md) - Testing updates

### Partner Integration
- [SHARING_WITH_PARTNERS_README.md](SHARING_WITH_PARTNERS_README.md) - Overview
- [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md) - Technical details
- [PARTNER_INTEGRATION_CHECKLIST.md](PARTNER_INTEGRATION_CHECKLIST.md) - Checklist
- [PARTNER_INTEGRATION_IMPROVEMENTS.md](PARTNER_INTEGRATION_IMPROVEMENTS.md) - Improvements

### Troubleshooting
- [BUG_FIX_BIAS_EVENTS.md](BUG_FIX_BIAS_EVENTS.md) - Known issues and fixes

---

## 💡 Tips

- **New to the project?** Start with [README.md](../README.md) and **[CAPABILITIES_OVERVIEW.md](CAPABILITIES_OVERVIEW.md)**
- **Need quick reference?** Use [KAFKA_QUICK_REFERENCE.md](KAFKA_QUICK_REFERENCE.md)
- **Integrating as partner?** Go to [SHARING_WITH_PARTNERS_README.md](SHARING_WITH_PARTNERS_README.md)
- **Testing?** Follow [TEST_COMPLETE_FLOW.md](TEST_COMPLETE_FLOW.md)
- **User-files (chatbot)?** See [USER_FILES_README.md](USER_FILES_README.md)
- **GraphDB init from backup?** See [GRAPHDB_README.md](GRAPHDB_README.md) and [graphdb_init/README.md](../graphdb_init/README.md)

---

## 📝 Documentation Standards

All documentation in this folder follows these principles:
- ✅ Clear structure with table of contents
- ✅ Step-by-step instructions
- ✅ Code examples with syntax highlighting
- ✅ Architecture diagrams where applicable
- ✅ Quick reference sections
- ✅ Troubleshooting guides

---

## 🔄 Keep Documentation Updated

When adding new documentation:
1. Add the file to this `Documentation/` folder
2. Update this INDEX.md with a link
3. Update the appropriate sections in the main README.md
4. Add cross-references to related documents

---

Last updated: February 2025

