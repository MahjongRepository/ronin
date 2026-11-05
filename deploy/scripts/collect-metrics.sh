#!/usr/bin/env bash
set -euo pipefail
umask 022

METRICS_DB="${METRICS_DB:-/opt/ronin/data/metrics/metrics.db}"
TELEGRAF_CONFIG="${TELEGRAF_CONFIG:-/opt/ronin/config/telegraf.conf}"
TELEGRAF_BIN="${TELEGRAF_BIN:-/usr/local/bin/telegraf}"
DEFAULT_RETENTION_DAYS=90
declare -A RETENTION_DAYS=([traefik]=30)

metrics_sql() {
  sqlite3 -cmd ".timeout 10000" "${METRICS_DB}" "$@"
}

run_collection() {
  metrics_sql "PRAGMA journal_mode=DELETE;" > /dev/null || return 1
  BOOT="$(head -c 8 /proc/sys/kernel/random/boot_id)" || return 1
  export BOOT METRICS_DB
  "${TELEGRAF_BIN}" --strict-env-handling --config "${TELEGRAF_CONFIG}" --once
}

run_maintenance() {
  local now tables table days statements=""
  now="$(date +%s)"
  tables="$(metrics_sql "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%';")" || return 1
  for table in ${tables}; do
    days="${RETENTION_DAYS[${table}]:-${DEFAULT_RETENTION_DAYS}}"
    statements+="CREATE INDEX IF NOT EXISTS \"idx_${table}_timestamp\" ON \"${table}\" (timestamp);"
    statements+="DELETE FROM \"${table}\" WHERE timestamp < $((now - days * 86400));"
  done
  if [[ -n "${statements}" ]]; then
    metrics_sql "BEGIN;${statements}COMMIT;"
  fi
}

collection_status=0
if ! run_collection; then
  collection_status=1
  echo "metrics collection failed" >&2
fi

maintenance_status=0
if ! run_maintenance; then
  maintenance_status=1
  echo "metrics maintenance failed" >&2
fi

if (( collection_status != 0 || maintenance_status != 0 )); then
  exit 1
fi
