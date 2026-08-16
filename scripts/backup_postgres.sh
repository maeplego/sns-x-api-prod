#!/usr/bin/env bash
# Backup sns_x_prod via pg_dump (Compose host port 5434 by default).
set -euo pipefail

HOST="${POSTGRES_HOST:-localhost}"
PORT="${POSTGRES_PORT:-5434}"
USER="${POSTGRES_USER:-sns}"
DB="${POSTGRES_DB:-sns_x_prod}"
OUT="${1:-backup_$(date +%Y%m%d_%H%M%S).dump}"

echo "Dumping ${DB} @ ${HOST}:${PORT} -> ${OUT}"
PGPASSWORD="${POSTGRES_PASSWORD:-sns}" pg_dump \
  -h "${HOST}" -p "${PORT}" -U "${USER}" -d "${DB}" -Fc -f "${OUT}"
echo "Done: ${OUT}"
