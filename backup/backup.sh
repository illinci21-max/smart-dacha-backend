#!/bin/bash
# Daily PostgreSQL backup -> custom archive -> upload to Backblaze B2 via rclone.
#
# Required env vars:
#   POSTGRES_HOST, POSTGRES_PORT (default 5432), POSTGRES_DB,
#   POSTGRES_USER, POSTGRES_PASSWORD,
#   RCLONE_REMOTE (e.g. "b2"), RCLONE_BUCKET (bucket name)
# Optional:
#   HEALTHCHECK_URL - POST after success (Healthchecks.io ping URL)
#   LOCAL_RETENTION_DAYS (default 7)
#   REMOTE_RETENTION_DAYS (default 90)

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups"
BACKUP_FILE="${BACKUP_DIR}/postgres_${POSTGRES_DB}_${TIMESTAMP}.dump"
LOG_PREFIX="[backup ${TIMESTAMP}]"

LOCAL_RETENTION_DAYS="${LOCAL_RETENTION_DAYS:-7}"
REMOTE_RETENTION_DAYS="${REMOTE_RETENTION_DAYS:-90}"
RCLONE_CONFIG_PATH="${RCLONE_CONFIG_PATH:-/etc/rclone/rclone.conf}"

mkdir -p "${BACKUP_DIR}"

echo "${LOG_PREFIX} Starting backup of ${POSTGRES_DB}"
echo "${LOG_PREFIX} Target file: ${BACKUP_FILE}"

PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT:-5432}" \
    --username="${POSTGRES_USER}" \
    --dbname="${POSTGRES_DB}" \
    --format=custom \
    --compress=6 \
    --no-owner \
    --no-privileges \
    --verbose \
    > "${BACKUP_FILE}" 2>"${BACKUP_FILE}.log" \
    || {
        echo "${LOG_PREFIX} ERROR: pg_dump failed. See ${BACKUP_FILE}.log"
        rm -f "${BACKUP_FILE}"
        exit 1
    }

SIZE=$(stat -c%s "${BACKUP_FILE}")
if [ "${SIZE}" -lt 1024 ]; then
    echo "${LOG_PREFIX} ERROR: Backup file suspiciously small (${SIZE} bytes)"
    rm -f "${BACKUP_FILE}"
    exit 1
fi

echo "${LOG_PREFIX} Local backup OK: ${SIZE} bytes"

if [ -n "${RCLONE_REMOTE:-}" ] && [ -n "${RCLONE_BUCKET:-}" ]; then
    if [ ! -f "${RCLONE_CONFIG_PATH}" ]; then
        echo "${LOG_PREFIX} WARN: rclone config not found at ${RCLONE_CONFIG_PATH}, skipping upload"
    else
        rclone copy "${BACKUP_FILE}" "${RCLONE_REMOTE}:${RCLONE_BUCKET}/postgres/" \
            --config="${RCLONE_CONFIG_PATH}" \
            --transfers=4 \
            --b2-chunk-size=96M \
            --progress=false \
            || {
                echo "${LOG_PREFIX} ERROR: rclone upload failed (file kept locally)"
                exit 1
            }
        echo "${LOG_PREFIX} Uploaded to ${RCLONE_REMOTE}:${RCLONE_BUCKET}/postgres/"
    fi
else
    echo "${LOG_PREFIX} WARN: RCLONE_REMOTE/BUCKET not set, upload skipped"
fi

find "${BACKUP_DIR}" -name "postgres_*.dump" -mtime +${LOCAL_RETENTION_DAYS} -delete || true
find "${BACKUP_DIR}" -name "*.log" -mtime +${LOCAL_RETENTION_DAYS} -delete || true

if [ -n "${RCLONE_REMOTE:-}" ] && [ -n "${RCLONE_BUCKET:-}" ] && [ -f "${RCLONE_CONFIG_PATH}" ]; then
    rclone delete "${RCLONE_REMOTE}:${RCLONE_BUCKET}/postgres/" \
        --config="${RCLONE_CONFIG_PATH}" \
        --min-age "${REMOTE_RETENTION_DAYS}d" \
        --include "postgres_*.dump" \
        || echo "${LOG_PREFIX} WARN: remote cleanup had errors (non-fatal)"
fi

if [ -n "${HEALTHCHECK_URL:-}" ]; then
    curl -fsS -m 10 --retry 3 -X POST "${HEALTHCHECK_URL}" -o /dev/null \
        || echo "${LOG_PREFIX} WARN: healthcheck ping failed"
fi

echo "${LOG_PREFIX} Backup complete: ${BACKUP_FILE} (${SIZE} bytes)"
