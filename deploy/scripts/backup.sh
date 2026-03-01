#!/usr/bin/env bash
# Backup SQLite databases and replays to a local restic repository.
set -euo pipefail

RONIN_DIR="/opt/ronin"
REPO="${RONIN_DIR}/backups"
STAGING="${RONIN_DIR}/data/backup-staging"

# restic needs RESTIC_PASSWORD and RESTIC_REPOSITORY
set -a
source "${RONIN_DIR}/.env.system"
set +a
export RESTIC_REPOSITORY="${REPO}"

cleanup() { rm -rf "${STAGING}"; }
trap cleanup EXIT

# Stage SQLite database via .backup for a crash-safe snapshot
mkdir -p "${STAGING}/db"

RONIN_DB="${RONIN_DIR}/data/db/ronin.db"

if [ -f "${RONIN_DB}" ]; then
  sqlite3 "${RONIN_DB}" ".backup '${STAGING}/db/ronin.db'"
  echo "Staged ronin DB"
else
  echo "ERROR: No database found to back up"
  exit 1
fi

# Run restic backup: staged DBs + replays
restic backup \
  "${STAGING}/db" \
  "${RONIN_DIR}/data/replays"

echo "Backup complete"

# Apply retention policy: 7 daily, 4 weekly, 3 monthly
restic forget \
  --keep-daily 7 \
  --keep-weekly 4 \
  --keep-monthly 3 \
  --prune

echo "Retention policy applied"
