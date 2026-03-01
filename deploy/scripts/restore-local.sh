#!/usr/bin/env bash
# Restore a downloaded server backup into the local development environment.
# Replaces backend/storage.db and backend/data/replays/ with server data.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"

ARCHIVE="/tmp/ronin-backup.tar.gz"
STAGING="/tmp/ronin-backup-restore"

if [ ! -f "$ARCHIVE" ]; then
  echo "ERROR: No backup archive found at $ARCHIVE"
  exit 1
fi

cleanup() { rm -rf "$STAGING" "$ARCHIVE"; }
trap cleanup EXIT

mkdir -p "$STAGING"
tar xzf "$ARCHIVE" -C "$STAGING"

# Restore DB: ronin DB becomes the local dev DB (backend/storage.db)
LOCAL_DB="$PROJECT_DIR/backend/storage.db"
RONIN_DB="$STAGING/db/ronin.db"

if [ -f "$LOCAL_DB" ]; then
  cp "$LOCAL_DB" "${LOCAL_DB}.bak"
  echo "Backed up existing DB to storage.db.bak"
fi

if [ -f "$RONIN_DB" ]; then
  cp "$RONIN_DB" "$LOCAL_DB"
  rm -f "${LOCAL_DB}-wal" "${LOCAL_DB}-shm"
  echo "Restored ronin DB -> backend/storage.db"
else
  echo "WARNING: No ronin DB found in backup"
fi

# Restore replays (clear first to remove files not in the snapshot)
REPLAY_SRC="$STAGING/replays"
REPLAY_DST="$PROJECT_DIR/backend/data/replays"

if [ -d "$REPLAY_SRC" ]; then
  rm -rf "$REPLAY_DST"
  mkdir -p "$REPLAY_DST"
  cp -a "$REPLAY_SRC/." "$REPLAY_DST/"
  echo "Restored replays → backend/data/replays/"
else
  echo "WARNING: No replays found in backup"
fi

echo "Local restore complete"
