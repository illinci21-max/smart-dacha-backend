#!/bin/bash
# Restore PostgreSQL from a backup.
#
# Usage:
#   restore.sh <filename>           # restore from local /backups/<filename>
#   restore.sh s3:<filename>        # download from B2 then restore
#
# WARNING: This DROPS existing data and replaces it with backup contents.

set -euo pipefail

if [ -z "${1:-}" ]; then
    cat <<EOF
Usage: restore.sh <backup_filename>

Examples:
  restore.sh postgres_smartdacha_20260506_031500.dump
  restore.sh s3:postgres_smartdacha_20260506_031500.dump

To list available backups:
  Local:  ls -lh /backups/
  Remote: rclone ls \$RCLONE_REMOTE:\$RCLONE_BUCKET/postgres/
EOF
    exit 1
fi

INPUT="${1}"
BACKUP_DIR="/backups"
RCLONE_CONFIG_PATH="${RCLONE_CONFIG_PATH:-/etc/rclone/rclone.conf}"

if [[ "${INPUT}" == s3:* ]]; then
    KEY="${INPUT#s3:}"
    LOCAL_FILE="${BACKUP_DIR}/${KEY}"
    if [ ! -f "${LOCAL_FILE}" ]; then
        echo "Downloading from ${RCLONE_REMOTE}:${RCLONE_BUCKET}/postgres/${KEY}..."
        rclone copy "${RCLONE_REMOTE}:${RCLONE_BUCKET}/postgres/${KEY}" "${BACKUP_DIR}/" \
            --config="${RCLONE_CONFIG_PATH}"
    fi
else
    LOCAL_FILE="${BACKUP_DIR}/${INPUT}"
fi

if [ ! -f "${LOCAL_FILE}" ]; then
    echo "ERROR: Backup file not found: ${LOCAL_FILE}"
    exit 1
fi

cat <<EOF

================================================================
              DESTRUCTIVE OPERATION WARNING
================================================================

This will DROP all existing data in:
  Database: ${POSTGRES_DB}
  Host:     ${POSTGRES_HOST}

And replace it with contents of:
  ${LOCAL_FILE}

Existing data will be LOST.

Type 'RESTORE' (uppercase) to confirm:
EOF

read -r CONFIRM
if [ "${CONFIRM}" != "RESTORE" ]; then
    echo "Aborted (got: '${CONFIRM}')."
    exit 1
fi

echo "Starting restore..."

PGPASSWORD="${POSTGRES_PASSWORD}" pg_restore \
    --host="${POSTGRES_HOST}" \
    --port="${POSTGRES_PORT:-5432}" \
    --username="${POSTGRES_USER}" \
    --dbname="${POSTGRES_DB}" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    --verbose \
    "${LOCAL_FILE}"

echo "Restore complete."
