#!/usr/bin/env bash
# Restore databases and replays from a restic snapshot.
set -euo pipefail

SNAPSHOT="${1:-latest}"
RONIN_DIR="/opt/ronin"
REPO="${RONIN_DIR}/backups"
STAGING="${RONIN_DIR}/data/restore-staging"

# restic needs RESTIC_PASSWORD and RESTIC_REPOSITORY
set -a
source "${RONIN_DIR}/.env.system"
set +a
export RESTIC_REPOSITORY="${REPO}"

cleanup() { rm -rf "${STAGING}"; }
trap cleanup EXIT

echo "Restoring snapshot: ${SNAPSHOT}"

# Stop application containers
cd "${RONIN_DIR}"
docker compose stop lobby game
echo "Stopped lobby and game containers"

# Restore into staging directory
mkdir -p "${STAGING}"
restic restore "${SNAPSHOT}" --target "${STAGING}"

# Restore databases (remove WAL/SHM to avoid stale state)
STAGED_DB="${STAGING}/opt/ronin/data/backup-staging/db"
if [ -d "${STAGED_DB}/lobby" ]; then
  rm -f "${RONIN_DIR}/data/db/lobby/lobby.db-wal" "${RONIN_DIR}/data/db/lobby/lobby.db-shm"
  cp "${STAGED_DB}/lobby/lobby.db" "${RONIN_DIR}/data/db/lobby/lobby.db"
  echo "Restored lobby DB"
fi

if [ -d "${STAGED_DB}/game" ]; then
  rm -f "${RONIN_DIR}/data/db/game/game.db-wal" "${RONIN_DIR}/data/db/game/game.db-shm"
  cp "${STAGED_DB}/game/game.db" "${RONIN_DIR}/data/db/game/game.db"
  echo "Restored game DB"
fi

# Restore replays
STAGED_REPLAYS="${STAGING}/opt/ronin/data/replays"
if [ -d "${STAGED_REPLAYS}" ]; then
  cp -a "${STAGED_REPLAYS}/." "${RONIN_DIR}/data/replays/"
  echo "Restored replays"
fi

# Fix ownership to match the app user in the Docker container
chown -R 1000:1000 "${RONIN_DIR}/data"

# Restart services
docker compose up -d
echo "Services restarted"
echo "Restore complete"
