# GraphDB Data Migration Guide

## Why is GraphDB empty on a new machine?

When you run the Dockerized app on a **new machine**:

- **MongoDB**, **MinIO**, **Kafka** use **named Docker volumes** (`mongodb_data`, `minio_data`, etc.).
- On a new host, Docker creates **new empty** volumes with those names.
- So GraphDB’s volume `graphdb_data` is **empty** on the new machine; your existing repositories and triples stay on the old host.

The app code and config are the same; only the **data** inside the GraphDB volume does not move with the project.

---

## Options for transferring GraphDB data

### Option 1: Backup and restore the GraphDB volume (recommended)

Use this when you want to move the **exact** GraphDB state (all repositories, config, indexes) to another machine.

#### On the **source** machine (where GraphDB already has data)

1. **Stop GraphDB** so the data is consistent:
   ```bash
   docker-compose stop graphdb
   ```

2. **Create a backup** of the volume (from the project root):
   ```bash
   # Linux/macOS (creates graphdb_backup_YYYYMMDD.tar.gz in current directory)
   docker run --rm -v data-warehouse-app_graphdb_data:/data -v "$(pwd):/backup" alpine tar czf /backup/graphdb_backup_$(date +%Y%m%d).tar.gz -C /data .

   # Windows PowerShell
   docker run --rm -v data-warehouse-app_graphdb_data:/data -v "${PWD}:/backup" alpine tar czf /backup/graphdb_backup_$(Get-Date -Format "yyyyMMdd").tar.gz -C /data .
   ```

   Or use the helper script:
   ```bash
   # Linux/macOS
   ./scripts/backup-graphdb.sh

   # Script creates: graphdb_backup_YYYYMMDD.tar.gz
   ```

3. **Start GraphDB again** on the source machine:
   ```bash
   docker-compose start graphdb
   ```

4. **Copy the backup file** to the new machine (USB, SCP, shared drive, etc.):
   ```bash
   scp graphdb_backup_YYYYMMDD.tar.gz user@new-machine:/path/to/data-warehouse-app/
   ```

#### On the **new** machine

1. **Start the stack once** so the GraphDB volume exists:
   ```bash
   docker-compose up -d
   ```

2. **Stop GraphDB**:
   ```bash
   docker-compose stop graphdb
   ```

3. **Restore** the backup into the volume:
   ```bash
   # Linux/macOS (replace YYYYMMDD with your backup date)
   docker run --rm -v data-warehouse-app_graphdb_data:/data -v "$(pwd):/backup" alpine sh -c "cd /data && tar xzf /backup/graphdb_backup_YYYYMMDD.tar.gz"

   # Windows PowerShell
   docker run --rm -v data-warehouse-app_graphdb_data:/data -v "${PWD}:/backup" alpine sh -c "cd /data && tar xzf /backup/graphdb_backup_YYYYMMDD.tar.gz"
   ```

   Or use the helper script:
   ```bash
   ./scripts/restore-graphdb.sh graphdb_backup_YYYYMMDD.tar.gz
   ```

4. **Start GraphDB** again:
   ```bash
   docker-compose start graphdb
   ```

After that, the new machine’s GraphDB will have the same data as the source.

---

### Option 2: Bind mount (data in a project folder)

If you keep GraphDB data in a **folder on disk** (e.g. `./graphdb_data`) instead of a named volume, you can copy that folder to the new machine with the rest of the project (or via rsync/scp).

#### Use the override file

An override file is provided so GraphDB uses a bind mount:

```bash
# Start with bind mount (creates ./graphdb_data on first run)
docker-compose -f docker-compose.yml -f docker-compose.graphdb-bind.yml up -d
```

- **First run:** GraphDB will create and use `./graphdb_data`.
- **Migration:** Copy the whole project (including `graphdb_data/`) to the new machine, or copy only `graphdb_data/` into the same path in the project on the new machine.
- **New machine:** Run the same command; GraphDB will use the copied data.

**Notes:**

- Add `graphdb_data/` to `.gitignore` (already done) so you don’t commit large binary data.
- Backup by copying or archiving the `graphdb_data` folder.
- Restore by placing that folder in the project root and starting with the override again.

---

### Option 3: Export/import via GraphDB (RDF or Recovery API)

Use this when you only need **repository contents** (e.g. RDF) and are okay recreating repositories by import.

- **Export:** From the running GraphDB Workbench (http://localhost:7200) or [GraphDB Recovery API](https://graphdb.ontotext.com/documentation/10.0/backing-up-and-recovering-repo.html), export repositories (e.g. RDF/TriG or backup).
- **New machine:** Start GraphDB with empty volume, create the same repositories, then import the exported files (Workbench → Import, or REST API).

This is more manual and depends on how you create repositories and run imports; it’s useful when you don’t want to move the full volume.

---

## Summary

| Goal | Suggested approach |
|------|---------------------|
| Clone full GraphDB state to another machine | **Option 1**: Backup volume → copy tar → restore volume on new host |
| Prefer a folder you can copy with the project | **Option 2**: Use `docker-compose.graphdb-bind.yml` and copy `graphdb_data/` |
| Only move RDF / specific repos | **Option 3**: Export from GraphDB, then import on the new instance |

---

## Volume name on your system

The GraphDB volume name is usually **`<project_dir>_graphdb_data`**, where `project_dir` is the directory that contains `docker-compose.yml` (e.g. `data-warehouse-app_graphdb_data`).

To list volumes and confirm the name:

```bash
docker volume ls | grep graphdb
```

Use that name in the `docker run` backup/restore commands above if you’re not using the scripts.
