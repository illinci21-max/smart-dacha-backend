# Smart Dacha - Backup Service

Daily PostgreSQL backups uploaded to Backblaze B2-compatible storage via rclone.

## What It Does

1. Every day at 03:15 Kyiv time, runs `pg_dump` of the production database.
2. Writes a compressed PostgreSQL custom-format archive (`.dump`).
3. Uploads it to the Backblaze B2 bucket via rclone.
4. Keeps local backups for 7 days in the `backup_data` Docker volume.
5. Keeps remote backups for 90 days in B2.
6. Pings Healthchecks.io on success.

## Setup

Prerequisites:

- Backblaze B2 bucket and Application Key.
- Healthchecks.io check URL, optional but recommended.
- Real credentials stored outside git.

On the VPS:

```bash
cd /home/deploy/smart-dacha-backend/backend
mkdir -p secrets
cp backup/rclone.conf.example secrets/rclone.conf
# Edit secrets/rclone.conf with real Backblaze credentials.
chmod 600 secrets/rclone.conf
```

Add to `.env.production` or `.env` used by Compose:

```env
BACKUP_BUCKET=smart-dacha-backups-illinci21
BACKUP_RCLONE_REMOTE=b2
BACKUP_HEALTHCHECK_URL=https://hc-ping.com/your-uuid-here
BACKUP_LOCAL_RETENTION_DAYS=7
BACKUP_REMOTE_RETENTION_DAYS=90
```

Start with production overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production up -d backup
```

To make this command default for the production VPS, set it in the shell:

```bash
export COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml
```

Then `docker compose --profile production up -d backup` works as before.
Regular development `docker compose up` does not load the backup service.

## Verify It Works

Note: all commands below assume `COMPOSE_FILE` includes both files, or use explicit `-f` flags such as `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backup ...`.

Run a manual backup:

```bash
docker compose exec backup /usr/local/bin/backup.sh
```

Expected ending:

```text
[backup TIMESTAMP] Backup complete: /backups/postgres_smartdacha_TIMESTAMP.dump
```

Check local backups:

```bash
docker compose exec backup ls -lh /backups/
```

Check remote backups:

```bash
docker compose exec backup rclone ls b2:smart-dacha-backups-illinci21/postgres/ --config=/etc/rclone/rclone.conf
```

Check cron logs:

```bash
docker compose logs backup --tail=50
```

## Restore Procedure

Warning: restore is destructive. It replaces data in the target database.

From a local backup:

```bash
docker compose exec backup /usr/local/bin/restore.sh postgres_smartdacha_20260506_031500.dump
```

From B2:

```bash
docker compose exec backup /usr/local/bin/restore.sh s3:postgres_smartdacha_20260506_031500.dump
```

Type `RESTORE` when prompted.

## Monthly Restore Drill

Test backups by restoring into a temporary database:

```bash
docker run -d --name pg-restore-test \
  -e POSTGRES_USER=smartdacha \
  -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=smartdacha \
  -p 15432:5432 postgres:16

sleep 10

LATEST=$(docker compose exec backup sh -lc 'ls -t /backups/postgres_*.dump | head -1')

docker compose exec \
  -e POSTGRES_HOST=host.docker.internal \
  -e POSTGRES_PORT=15432 \
  -e POSTGRES_DB=smartdacha \
  -e POSTGRES_USER=smartdacha \
  -e POSTGRES_PASSWORD=test \
  backup /usr/local/bin/restore.sh "$(basename "$LATEST")"

docker exec pg-restore-test psql -U smartdacha -d smartdacha \
  -c "SELECT count(*) FROM users;"

docker rm -f pg-restore-test
```

## Cost Estimate

Backblaze B2 storage is approximately $0.005/GB/month, with the first 10 GB free.

Example: 1 GB compressed daily backup with 90-day retention is about 90 GB, or roughly $0.45/month.

## Troubleshooting

### `POSTGRES_PASSWORD is required`

Set `POSTGRES_PASSWORD` in your Compose env file. This repo intentionally uses fail-fast `${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}`.

### `BACKUP_BUCKET is required for backup service`

Set `BACKUP_BUCKET` before starting the `production` profile.

### Backup runs but does not upload

Check that `secrets/rclone.conf` exists and is mounted:

```bash
docker compose exec backup rclone lsd b2: --config=/etc/rclone/rclone.conf
```

### Healthchecks.io shows the check as down

Check backup logs first:

```bash
docker compose logs backup --tail=100
```

Common causes: failed `pg_dump`, network failure, typo in `BACKUP_HEALTHCHECK_URL`.

### Disk fills up

Reduce local retention or inspect old backups:

```bash
docker compose exec backup find /backups -name "postgres_*.dump" -mtime +7
```

## Security Notes

- `secrets/rclone.conf` contains the B2 application key. Keep it outside git and mount it read-only.
- Use a B2 application key restricted to the backup bucket.
- Backups are compressed PostgreSQL custom archives, not application-level encrypted archives.
- Database password is passed via environment variables, not embedded in scripts.
