# Multi-Installation Deployment & Data Synchronization Guide

## Overview

This guide addresses deployment scenarios where the Data Warehouse (DW) needs to be installed on multiple machines while maintaining data consistency and user account synchronization across installations.

---

## 🏗️ Architecture Options

### Option 1: Hub-and-Spoke (Centralized Hub) ⭐ **Recommended**

**Architecture:**
```
┌─────────────────────────────────────────┐
│         Central Hub (Main Server)       │
│  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │ MongoDB  │  │  MinIO   │  │ Kafka  ││
│  │ (Master) │  │ (Master) │  │        ││
│  └──────────┘  └──────────┘  └────────┘│
│         │            │            │     │
│         └────────────┴────────────┘     │
│                  │                      │
│            ┌─────┴─────┐               │
│            │  DW API   │               │
│            │  (Hub)    │               │
│            └─────┬─────┘               │
└──────────────────┼──────────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│  Node 1  │ │  Node 2  │ │  Node 3  │
│ (Spoke)  │ │ (Spoke)  │ │ (Spoke)  │
│          │ │          │ │          │
│ ┌──────┐ │ │ ┌──────┐ │ │ ┌──────┐ │
│ │ DW   │ │ │ │ DW   │ │ │ │ DW   │ │
│ │ API  │ │ │ │ API  │ │ │ │ API  │ │
│ └──────┘ │ │ └──────┘ │ │ └──────┘ │
│          │ │          │ │          │
│ ┌──────┐ │ │ ┌──────┐ │ │ ┌──────┐ │
│ │Local │ │ │ │Local │ │ │ │Local │ │
│ │Cache │ │ │ │Cache │ │ │ │Cache │ │
│ └──────┘ │ │ └──────┘ │ │ └──────┘ │
└──────────┘ └──────────┘ └──────────┘
```

**How It Works:**
- **Central Hub**: Main server maintains the authoritative database (MongoDB) and file storage (MinIO)
- **Spoke Nodes**: Local installations connect to the hub for:
  - User authentication/authorization
  - Data reads (with local caching)
  - Data writes (synced to hub)
  - Periodic full sync for offline capability

**Pros:**
- ✅ Single source of truth (hub)
- ✅ Consistent user accounts across all nodes
- ✅ Centralized backup and management
- ✅ Easier to implement
- ✅ Supports offline mode with sync

**Cons:**
- ❌ Hub is a single point of failure (mitigate with replication)
- ❌ Requires internet connectivity for real-time sync
- ❌ Hub must handle all write traffic

**Use Case:** When you have a main server and multiple satellite installations that need to stay in sync.

---

### Option 2: Peer-to-Peer (Federated)

**Architecture:**
```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   Node 1     │◄────►│   Node 2     │◄────►│   Node 3     │
│              │      │              │      │              │
│ ┌──────────┐ │      │ ┌──────────┐ │      │ ┌──────────┐ │
│ │ MongoDB  │ │      │ │ MongoDB  │ │      │ │ MongoDB  │ │
│ │ (Local)  │ │      │ │ (Local)  │ │      │ │ (Local)  │ │
│ └──────────┘ │      │ └──────────┘ │      │ └──────────┘ │
│              │      │              │      │              │
│ ┌──────────┐ │      │ ┌──────────┐ │      │ ┌──────────┐ │
│ │  MinIO  │ │      │ │  MinIO   │ │      │ │  MinIO   │ │
│ │ (Local) │ │      │ │ (Local)  │ │      │ │ (Local)  │ │
│ └──────────┘ │      │ └──────────┘ │      │ └──────────┘ │
│              │      │              │      │              │
│   Sync API   │      │   Sync API   │      │   Sync API   │
└──────────────┘      └──────────────┘      └──────────────┘
```

**How It Works:**
- Each node maintains its own MongoDB and MinIO
- Nodes sync data bidirectionally via sync API
- Conflict resolution needed for concurrent edits
- User accounts replicated across all nodes

**Pros:**
- ✅ No single point of failure
- ✅ Works offline (full local data)
- ✅ Lower latency (local data access)

**Cons:**
- ❌ Complex conflict resolution
- ❌ Eventual consistency challenges
- ❌ More complex to implement
- ❌ Requires sync protocol design

**Use Case:** When nodes need to operate independently and sync periodically.

---

### Option 3: Hybrid (Hub + Local Cache)

**Architecture:**
```
┌─────────────────────────────────────────┐
│         Central Hub (Main Server)       │
│  ┌──────────┐  ┌──────────┐             │
│  │ MongoDB  │  │  MinIO   │             │
│  │ (Master) │  │ (Master) │             │
│  └──────────┘  └──────────┘             │
│         │            │                  │
│         └────────────┘                  │
│                  │                      │
│            ┌─────┴─────┐               │
│            │  DW API   │               │
│            │  (Hub)    │               │
│            └─────┬─────┘               │
└──────────────────┼──────────────────────┘
                   │
        ┌──────────┼──────────┐
        │          │          │
        ▼          ▼          ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│  Node 1  │ │  Node 2  │ │  Node 3  │
│          │ │          │ │          │
│ ┌──────┐ │ │ ┌──────┐ │ │ ┌──────┐ │
│ │Local │ │ │ │Local │ │ │ │Local │ │
│ │Mongo │ │ │ │Mongo │ │ │ │Mongo │ │
│ │Cache │ │ │ │Cache │ │ │ │Cache │ │
│ └──────┘ │ │ └──────┘ │ │ └──────┘ │
│          │ │          │ │          │
│ ┌──────┐ │ │ ┌──────┐ │ │ ┌──────┐ │
│ │Local │ │ │ │Local │ │ │ │Local │ │
│ │MinIO │ │ │ │MinIO │ │ │ │MinIO │ │
│ │Cache │ │ │ │Cache │ │ │ │Cache │ │
│ └──────┘ │ │ └──────┘ │ │ └──────┘ │
└──────────┘ └──────────┘ └──────────┘
```

**How It Works:**
- Hub maintains master data
- Nodes cache frequently accessed data locally
- Writes go to hub first, then replicate to local cache
- Reads prefer local cache, fallback to hub
- Periodic full sync for consistency

**Pros:**
- ✅ Best of both worlds
- ✅ Fast local reads
- ✅ Centralized writes
- ✅ Offline capability

**Cons:**
- ❌ Cache invalidation complexity
- ❌ More storage needed per node

**Use Case:** When you need fast local access but centralized control.

---

## 📊 Data Synchronization Strategy

### What Needs to Be Synced?

1. **User Accounts** (Critical)
   - User IDs, usernames, emails
   - Authentication credentials (hashed passwords)
   - User preferences and settings

2. **Dataset Metadata** (Critical)
   - Dataset IDs, names, descriptions
   - Versions, file paths, metadata
   - Tags, custom metadata

3. **Dataset Files** (Large, Optional)
   - Actual CSV, images, models, etc.
   - Can be synced on-demand or selectively

4. **AI Models** (Large, Optional)
   - Model files and metadata
   - Training history

5. **Reports** (Medium Priority)
   - Bias reports
   - Transformation reports
   - XAI reports

6. **GraphDB Data** (Optional)
   - Semantic knowledge graphs
   - Can be synced separately

---

## 🔄 Recommended Implementation: Hub-and-Spoke with Sync API

### Step 1: Add Sync Endpoints to DW API

Create new sync endpoints in `app/api/sync.py`:

```python
from fastapi import APIRouter, HTTPException, Query, Header
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import json

router = APIRouter(prefix="/sync", tags=["Synchronization"])

@router.get("/users")
async def sync_users(
    last_sync: Optional[datetime] = Query(None, description="Last sync timestamp"),
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Sync user accounts from hub to node.
    Returns all users or only those modified since last_sync.
    """
    # Verify API key (node authentication)
    if not verify_node_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Query users modified since last_sync
    query = {}
    if last_sync:
        query["updated_at"] = {"$gte": last_sync}
    
    users = await metadata_service.get_users(query)
    return {
        "timestamp": datetime.now(tz=timezone.utc),
        "users": [user.dict() for user in users]
    }

@router.get("/datasets")
async def sync_datasets(
    user_id: Optional[str] = Query(None),
    last_sync: Optional[datetime] = Query(None),
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Sync dataset metadata from hub to node.
    """
    # Verify API key
    if not verify_node_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Query datasets
    query = {}
    if user_id:
        query["user_id"] = user_id
    if last_sync:
        query["updated_at"] = {"$gte": last_sync}
    
    datasets = await metadata_service.get_datasets(query)
    return {
        "timestamp": datetime.now(tz=timezone.utc),
        "datasets": [ds.dict() for ds in datasets]
    }

@router.post("/datasets/push")
async def push_dataset(
    dataset_data: Dict[str, Any],
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Push dataset from node to hub (for writes from nodes).
    """
    # Verify API key
    if not verify_node_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Create/update dataset on hub
    dataset = await metadata_service.create_or_update_dataset(dataset_data)
    return {"status": "success", "dataset": dataset.dict()}

@router.get("/files/{user_id}/{dataset_id}/{version}")
async def sync_file(
    user_id: str,
    dataset_id: str,
    version: str,
    api_key: str = Header(..., alias="X-API-Key")
):
    """
    Download file from hub (for on-demand file sync).
    """
    # Verify API key
    if not verify_node_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Download file from MinIO
    file_data = await file_service.download_dataset_file(
        user_id, dataset_id, version
    )
    return file_data

@router.get("/status")
async def sync_status(api_key: str = Header(..., alias="X-API-Key")):
    """
    Get sync status and last sync timestamps.
    """
    if not verify_node_api_key(api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return {
        "hub_version": "1.0.0",
        "last_user_sync": await get_last_sync_timestamp("users", api_key),
        "last_dataset_sync": await get_last_sync_timestamp("datasets", api_key),
        "total_users": await metadata_service.count_users(),
        "total_datasets": await metadata_service.count_datasets()
    }
```

### Step 2: Create Node Sync Client

Create `sync_client.py` for nodes to sync with hub:

```python
"""
Sync client for node installations to sync with central hub.
"""
import asyncio
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class HubSyncClient:
    def __init__(
        self,
        hub_url: str,
        api_key: str,
        node_id: str
    ):
        self.hub_url = hub_url.rstrip('/')
        self.api_key = api_key
        self.node_id = node_id
        self.headers = {
            "X-API-Key": api_key,
            "X-Node-ID": node_id
        }
    
    def sync_users(self, last_sync: Optional[datetime] = None) -> List[Dict]:
        """Sync users from hub to local node."""
        url = f"{self.hub_url}/sync/users"
        params = {}
        if last_sync:
            params["last_sync"] = last_sync.isoformat()
        
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        logger.info(f"Synced {len(data['users'])} users from hub")
        return data['users']
    
    def sync_datasets(
        self,
        user_id: Optional[str] = None,
        last_sync: Optional[datetime] = None
    ) -> List[Dict]:
        """Sync dataset metadata from hub to local node."""
        url = f"{self.hub_url}/sync/datasets"
        params = {}
        if user_id:
            params["user_id"] = user_id
        if last_sync:
            params["last_sync"] = last_sync.isoformat()
        
        response = requests.get(url, headers=self.headers, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        
        logger.info(f"Synced {len(data['datasets'])} datasets from hub")
        return data['datasets']
    
    def push_dataset(self, dataset_data: Dict[str, Any]) -> Dict:
        """Push dataset from node to hub."""
        url = f"{self.hub_url}/sync/datasets/push"
        response = requests.post(
            url,
            headers=self.headers,
            json=dataset_data,
            timeout=60
        )
        response.raise_for_status()
        return response.json()
    
    def download_file(
        self,
        user_id: str,
        dataset_id: str,
        version: str
    ) -> bytes:
        """Download file from hub (on-demand)."""
        url = f"{self.hub_url}/sync/files/{user_id}/{dataset_id}/{version}"
        response = requests.get(url, headers=self.headers, timeout=300, stream=True)
        response.raise_for_status()
        return response.content
    
    def get_sync_status(self) -> Dict:
        """Get sync status from hub."""
        url = f"{self.hub_url}/sync/status"
        response = requests.get(url, headers=self.headers, timeout=10)
        response.raise_for_status()
        return response.json()
    
    def full_sync(self) -> Dict:
        """Perform full sync (users + datasets)."""
        logger.info("Starting full sync from hub...")
        
        # Sync users
        users = self.sync_users()
        logger.info(f"Synced {len(users)} users")
        
        # Sync datasets
        datasets = self.sync_datasets()
        logger.info(f"Synced {len(datasets)} datasets")
        
        return {
            "users_count": len(users),
            "datasets_count": len(datasets),
            "timestamp": datetime.now(tz=timezone.utc).isoformat()
        }
```

### Step 3: Node Configuration

Add to `.env` for node installations:

```env
# Hub connection (for sync)
HUB_URL=https://hub.example.com:8000
HUB_API_KEY=your-node-api-key-here
NODE_ID=node-001

# Local storage (for caching)
LOCAL_MONGODB_URL=mongodb://localhost:27017
LOCAL_MINIO_ENDPOINT=localhost:9000

# Sync settings
SYNC_INTERVAL_SECONDS=300  # Sync every 5 minutes
ENABLE_OFFLINE_MODE=true   # Allow local operations when hub is offline
```

### Step 4: Sync Service (Node Side)

Create `app/services/sync_service.py`:

```python
"""
Sync service for node installations.
Handles periodic sync with hub and local caching.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
from sync_client import HubSyncClient
from app.services.metadata_service import MetadataService

logger = logging.getLogger(__name__)

class NodeSyncService:
    def __init__(
        self,
        hub_url: str,
        api_key: str,
        node_id: str,
        sync_interval: int = 300
    ):
        self.hub_client = HubSyncClient(hub_url, api_key, node_id)
        self.metadata_service = MetadataService()
        self.sync_interval = sync_interval
        self.last_sync = None
        self.sync_task = None
    
    async def start_periodic_sync(self):
        """Start periodic sync task."""
        self.sync_task = asyncio.create_task(self._sync_loop())
        logger.info("Periodic sync started")
    
    async def stop_periodic_sync(self):
        """Stop periodic sync task."""
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
        logger.info("Periodic sync stopped")
    
    async def _sync_loop(self):
        """Periodic sync loop."""
        while True:
            try:
                await self.sync_from_hub()
                await asyncio.sleep(self.sync_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sync error: {e}")
                await asyncio.sleep(60)  # Retry after 1 minute
    
    async def sync_from_hub(self):
        """Sync data from hub to local node."""
        try:
            # Sync users
            users = self.hub_client.sync_users(self.last_sync)
            for user_data in users:
                await self.metadata_service.upsert_user(user_data)
            
            # Sync datasets
            datasets = self.hub_client.sync_datasets(last_sync=self.last_sync)
            for dataset_data in datasets:
                await self.metadata_service.upsert_dataset(dataset_data)
            
            self.last_sync = datetime.now(tz=timezone.utc)
            logger.info(f"Sync completed at {self.last_sync}")
            
        except Exception as e:
            logger.error(f"Failed to sync from hub: {e}")
            raise
    
    async def push_to_hub(self, dataset_data: dict):
        """Push dataset changes from node to hub."""
        try:
            result = self.hub_client.push_dataset(dataset_data)
            logger.info(f"Pushed dataset to hub: {result['dataset']['dataset_id']}")
            return result
        except Exception as e:
            logger.error(f"Failed to push to hub: {e}")
            raise
```

---

## 🔐 Security Considerations

### 1. Node Authentication

**API Key Management:**
- Each node gets a unique API key from hub
- Keys stored securely (environment variables, secrets manager)
- Keys can be rotated without downtime

**Implementation:**
```python
# app/core/config.py
class Settings(BaseSettings):
    # ... existing settings ...
    
    # Node sync settings
    NODE_API_KEYS: Dict[str, str] = {}  # node_id -> api_key
    HUB_API_KEY: Optional[str] = None  # For node installations
    
    class Config:
        env_file = ".env"
```

### 2. Data Encryption

- **In Transit**: Use HTTPS/TLS for all sync communications
- **At Rest**: Encrypt sensitive data in MongoDB (field-level encryption)
- **Files**: MinIO supports encryption at rest

### 3. Access Control

- Nodes can only sync data they're authorized for
- User-based access control maintained
- Audit logging for all sync operations

---

## 📋 Deployment Checklist

### Hub Installation (Main Server)

- [ ] Deploy Docker Compose stack
- [ ] Configure MongoDB with replication (for HA)
- [ ] Configure MinIO with replication (for HA)
- [ ] Set up SSL/TLS certificates
- [ ] Configure firewall rules
- [ ] Set up monitoring and alerts
- [ ] Create initial admin user
- [ ] Generate API keys for nodes
- [ ] Test sync endpoints

### Node Installation (Satellite)

- [ ] Deploy Docker Compose stack
- [ ] Configure local MongoDB (for caching)
- [ ] Configure local MinIO (for caching, optional)
- [ ] Set `HUB_URL` and `HUB_API_KEY` in `.env`
- [ ] Run initial full sync
- [ ] Start periodic sync service
- [ ] Test local operations
- [ ] Test sync with hub
- [ ] Configure offline mode (if needed)

---

## 🚀 Quick Start: Setting Up a Node

### 1. Clone and Configure

```bash
# Clone repository
git clone https://github.com/your-org/ALFIE-Data-Warehouse.git
cd ALFIE-Data-Warehouse

# Copy environment file
cp .env.example .env

# Edit .env
nano .env
```

Add node-specific settings:
```env
# Hub connection
HUB_URL=https://hub.example.com:8000
HUB_API_KEY=node-001-api-key-here
NODE_ID=node-001

# Local services (for caching)
MONGODB_URL=mongodb://localhost:27017
MINIO_ENDPOINT=localhost:9000

# Sync settings
SYNC_INTERVAL_SECONDS=300
ENABLE_OFFLINE_MODE=true
```

### 2. Start Services

```bash
# Start local services
docker-compose up -d mongodb minio

# Start API (will sync with hub)
docker-compose up -d api
```

### 3. Run Initial Sync

```python
# sync_initial.py
from sync_client import HubSyncClient
from datetime import datetime, timezone

hub_client = HubSyncClient(
    hub_url="https://hub.example.com:8000",
    api_key="node-001-api-key-here",
    node_id="node-001"
)

# Full sync
result = hub_client.full_sync()
print(f"Initial sync complete: {result}")
```

### 4. Verify Sync

```bash
# Check sync status
curl -H "X-API-Key: node-001-api-key-here" \
     https://hub.example.com:8000/sync/status
```

---

## 🔄 Sync Strategies

### Strategy 1: Real-Time Sync (Recommended for Hub-and-Spoke)

**When to Use:**
- Hub has reliable internet
- Nodes need up-to-date data
- Low latency requirements

**Implementation:**
- All writes go to hub first
- Hub immediately syncs to nodes
- Nodes cache reads locally

### Strategy 2: Periodic Sync

**When to Use:**
- Limited bandwidth
- Nodes can tolerate slight delays
- Cost optimization

**Implementation:**
- Nodes sync every N minutes (configurable)
- Only changed data since last sync
- Works well with `updated_at` timestamps

### Strategy 3: On-Demand Sync

**When to Use:**
- Very limited bandwidth
- Large files (datasets, models)
- User-initiated sync

**Implementation:**
- Metadata synced periodically
- Files downloaded on-demand when accessed
- User can trigger manual sync

### Strategy 4: Hybrid (Recommended)

**Combination:**
- **Users & Metadata**: Real-time or frequent periodic sync
- **Files**: On-demand download when accessed
- **Reports**: Periodic sync (less critical)

---

## 📊 Monitoring & Maintenance

### Sync Health Monitoring

Add to hub API:

```python
@router.get("/sync/health")
async def sync_health():
    """Monitor sync health across all nodes."""
    nodes = await get_registered_nodes()
    health = []
    
    for node in nodes:
        try:
            status = await check_node_health(node.node_id)
            health.append({
                "node_id": node.node_id,
                "status": "healthy" if status else "unhealthy",
                "last_sync": node.last_sync,
                "lag_seconds": (datetime.now() - node.last_sync).total_seconds()
            })
        except Exception as e:
            health.append({
                "node_id": node.node_id,
                "status": "error",
                "error": str(e)
            })
    
    return {"nodes": health}
```

### Backup Strategy

**Hub:**
- Daily MongoDB backups
- Daily MinIO backups (or replication)
- Backup retention: 30 days

**Nodes:**
- Local cache backups (optional)
- Can restore from hub if needed

---

## 💡 Recommendations

### For Your Use Case

Based on your description (main server + multiple installations), I recommend:

1. **Hub-and-Spoke Architecture** ⭐
   - Main server as hub
   - Satellite installations as nodes
   - Centralized user management
   - Distributed file access

2. **Hybrid Sync Strategy**
   - Users & metadata: Real-time or 5-minute periodic sync
   - Files: On-demand download (save bandwidth)
   - Reports: Periodic sync (daily or on-demand)

3. **Implementation Priority**
   - Phase 1: User account sync (critical)
   - Phase 2: Dataset metadata sync
   - Phase 3: On-demand file sync
   - Phase 4: Full bidirectional sync (if needed)

4. **Security**
   - API key authentication for nodes
   - HTTPS/TLS for all communications
   - Audit logging

---

## 📚 Additional Resources

- [MongoDB Replication Guide](https://docs.mongodb.com/manual/replication/)
- [MinIO Replication Guide](https://min.io/docs/minio/linux/administration/object-management/replication.html)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)

---

## ❓ FAQ

**Q: Should the DW keep copies of everything?**
A: Yes, the hub should maintain the authoritative copy. Nodes can cache selectively based on usage patterns.

**Q: What happens if a node goes offline?**
A: With offline mode enabled, nodes can continue operating locally. Changes are queued and synced when connection is restored.

**Q: How do we handle conflicts?**
A: Hub is the source of truth. Last-write-wins for metadata. For files, versioning handles conflicts.

**Q: Can nodes write directly to hub?**
A: Yes, nodes should write to hub first, then hub syncs back. This maintains consistency.

**Q: What about large files?**
A: Use on-demand download. Only sync file metadata, download actual files when needed.

---

Ready to implement! Start with user account sync, then expand to datasets and files. 🚀
