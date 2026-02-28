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

# Stage SQLite databases via .backup for crash-safe snapshots
mkdir -p "${STAGING}/db/lobby" "${STAGING}/db/game"

LOBBY_DB="${RONIN_DIR}/data/db/lobby/lobby.db"
GAME_DB="${RONIN_DIR}/data/db/game/game.db"

if [ -f "${LOBBY_DB}" ]; then
  sqlite3 "${LOBBY_DB}" ".backup '${STAGING}/db/lobby/lobby.db'"
  echo "Staged lobby DB"
fi

if [ -f "${GAME_DB}" ]; then
  sqlite3 "${GAME_DB}" ".backup '${STAGING}/db/game/game.db'"
  echo "Staged game DB"
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
