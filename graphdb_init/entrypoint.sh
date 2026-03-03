#!/bin/sh
set -e
GDB_HOME="${GDB_HOME:-/opt/graphdb/home}"
GDB_DATA="${GDB_HOME}/data"
INIT_BACKUP_DIR="${INIT_BACKUP_DIR:-/init-backup}"

# If data directory is empty and we have a backup, restore it
if [ -d "$INIT_BACKUP_DIR" ] && [ -n "$(ls -A "$INIT_BACKUP_DIR" 2>/dev/null)" ]; then
  BACKUP_FILE=$(find "$INIT_BACKUP_DIR" -maxdepth 1 -name '*.tar.gz' -type f | head -n 1)
  if [ -n "$BACKUP_FILE" ]; then
    if [ ! -f "${GDB_DATA}/.restored" ] && { [ ! -d "${GDB_DATA}/repositories" ] || [ -z "$(ls -A "${GDB_DATA}/repositories" 2>/dev/null)" ]; }; then
      echo "GraphDB data directory empty or missing repositories. Restoring from backup: $BACKUP_FILE"
      TMP_RESTORE="/tmp/graphdb_restore_$$"
      mkdir -p "$TMP_RESTORE"
      tar -xzf "$BACKUP_FILE" -C "$TMP_RESTORE"
      # Backup may be: (1) contents of "data" dir, (2) full "home" dir, or (3) single top-level dir (e.g. "data" or "repositories")
      if [ -d "${TMP_RESTORE}/data" ] && [ -n "$(ls -A "${TMP_RESTORE}/data" 2>/dev/null)" ]; then
        cp -a "${TMP_RESTORE}/data/." "$GDB_DATA/"
      elif [ -d "${TMP_RESTORE}/repositories" ]; then
        cp -a "${TMP_RESTORE}/." "$GDB_DATA/"
      elif [ -d "${TMP_RESTORE}/home/data" ]; then
        cp -a "${TMP_RESTORE}/home/data/." "$GDB_DATA/"
      else
        cp -a "${TMP_RESTORE}/." "$GDB_DATA/"
      fi
      rm -rf "$TMP_RESTORE"
      touch "${GDB_DATA}/.restored"
      echo "GraphDB backup restore completed."
    fi
  fi
fi

# Start GraphDB (default image command)
exec "$@"
