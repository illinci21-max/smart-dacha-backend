# Smart Dacha Backend - VPS Deployment Runbook

This runbook prepares a first production/staging VPS deploy for the backend.
It assumes Docker Compose deployment with GHCR images, PostgreSQL/TimescaleDB,
Redis, automated Backblaze B2 backups, and GitHub Actions manual deploys.

No real credentials belong in git. Keep production secrets in a password
manager and on the VPS only.

## Current Deployment Shape

- Repo: `github.com/illinci21-max/smart-dacha-backend`
- API image: `ghcr.io/illinci21-max/smart-dacha-backend:<tag>`
- Backup image: `ghcr.io/illinci21-max/smart-dacha-backup:<tag>`
- Compose base: `docker-compose.yml`
- Production overlay: `docker-compose.prod.yml`
- Backend path on VPS: `/opt/smart-dacha-backend`
- API health endpoint: `https://<API_DOMAIN>/health`

## Minimum VPS

Recommended starting point:

- Ubuntu 24.04 LTS
- 2 vCPU
- 4 GB RAM
- 60+ GB SSD
- IPv4 address
- Docker + Docker Compose plugin

For early staging, 1 vCPU / 2 GB RAM can work, but PostgreSQL, Redis, API,
Celery, and backups will be cramped. Production should start at 2 vCPU / 4 GB.

## DNS

Create DNS records before running the GitHub deploy workflow:

```text
api.smartdacha.ua    A      <VPS_IPV4>
```

Optional later:

```text
app.smartdacha.ua    A/CNAME    <frontend hosting target>
```

Wait until DNS resolves:

```bash
dig +short api.smartdacha.ua
```

## One-Time VPS Setup

Log in as root first:

```bash
ssh root@<VPS_IP>
```

Create a deploy user:

```bash
adduser deploy
usermod -aG sudo deploy
```

Install base packages:

```bash
apt-get update
apt-get install -y ca-certificates curl git ufw fail2ban jq
```

Install Docker:

```bash
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
usermod -aG docker deploy
```

Configure firewall:

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

Log out and back in as `deploy` so Docker group membership applies:

```bash
ssh deploy@<VPS_IP>
docker version
docker compose version
```

## Checkout Backend Repo

```bash
sudo mkdir -p /opt/smart-dacha-backend
sudo chown deploy:deploy /opt/smart-dacha-backend
cd /opt/smart-dacha-backend
git clone https://github.com/illinci21-max/smart-dacha-backend.git .
```

If the repo is private, use a deploy key or GitHub HTTPS token with read access.

## GHCR Login

The VPS must be able to pull private GHCR images.

Create a GitHub token with package read access, then:

```bash
echo "<GITHUB_PAT>" | docker login ghcr.io -u illinci21-max --password-stdin
```

Verify:

```bash
docker pull ghcr.io/illinci21-max/smart-dacha-backend:dev-test
docker pull ghcr.io/illinci21-max/smart-dacha-backup:dev-test
```

## Production Environment File

Create `.env` on the VPS:

```bash
cd /opt/smart-dacha-backend
cp .env.example .env
chmod 600 .env
nano .env
```

Minimum required production values:

```env
ENVIRONMENT=production
DEBUG=false
RELEASE_VERSION=dev-test

POSTGRES_PASSWORD=<strong-generated-password>
SECRET_KEY=<openssl-rand-hex-64>

CORS_ORIGINS=https://app.smartdacha.ua
FRONTEND_URL=https://app.smartdacha.ua

SENTRY_DSN=
PROMETHEUS_METRICS_ENABLED=true
LOG_FORMAT=json

BACKUP_BUCKET=smart-dacha-backups-illinci21
BACKUP_RCLONE_REMOTE=b2
BACKUP_HEALTHCHECK_URL=https://hc-ping.com/<uuid>
BACKUP_LOCAL_RETENTION_DAYS=7
BACKUP_REMOTE_RETENTION_DAYS=90
```

Generate secrets:

```bash
openssl rand -hex 32   # POSTGRES_PASSWORD
openssl rand -hex 64   # SECRET_KEY
```

## Backblaze B2 Backup Config

Create `secrets/rclone.conf`:

```bash
cd /opt/smart-dacha-backend
mkdir -p secrets
cp backup/rclone.conf.example secrets/rclone.conf
chmod 600 secrets/rclone.conf
nano secrets/rclone.conf
```

Fill in the Backblaze B2 key ID and application key from the password manager.
Do not commit this file.

Verify rclone inside the backup container after it starts:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production exec backup \
  rclone lsd b2: --config=/etc/rclone/rclone.conf
```

## Firebase Credentials

`docker-compose.yml` mounts:

```text
./firebase-credentials.json:/app/firebase-credentials.json:ro
```

If push notifications are enabled, place the real file on the VPS:

```bash
cd /opt/smart-dacha-backend
nano firebase-credentials.json
chmod 600 firebase-credentials.json
```

If Firebase is not used yet, keep a valid empty/placeholder strategy aligned
with the app settings before first production start.

## Pre-Deploy Checklist

Before the first real deploy:

- GitHub Actions `ci.yml` is green on `main`.
- GitHub Actions `build.yml` has pushed `dev-test` or a release tag to GHCR.
- VPS can `docker pull` API and backup images from GHCR.
- `.env` exists on VPS and is `chmod 600`.
- `secrets/rclone.conf` exists and is `chmod 600`.
- DNS for `API_DOMAIN` points to the VPS.
- TLS/reverse proxy is configured for `https://<API_DOMAIN>`.
- `POSTGRES_PASSWORD`, `SECRET_KEY`, B2 credentials, and Healthchecks URL are stored in the password manager.

Production image references live in `docker-compose.prod.yml`:

- `api`, `celery_worker`, `celery_beat` use `ghcr.io/illinci21-max/smart-dacha-backend:${RELEASE_TAG:-latest}`
- `backup` uses `ghcr.io/illinci21-max/smart-dacha-backup:${RELEASE_TAG:-latest}`

## First Manual Compose Start

Use this only for initial VPS smoke testing. Later deploys should use GitHub
Actions `deploy.yml`.

```bash
cd /opt/smart-dacha-backend
export RELEASE_TAG=dev-test

docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production config

docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production pull api celery_worker celery_beat backup

docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production up -d postgres redis

docker compose ps
```

Run migrations:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production run --rm api alembic upgrade head
```

Start app services:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production up -d api celery_worker celery_beat backup
```

Check:

```bash
docker compose ps
docker compose logs api --tail=100
curl -fsS http://localhost:8000/health | jq .
```

After reverse proxy/TLS is ready:

```bash
curl -fsS https://api.smartdacha.ua/health | jq .
```

Expected:

```json
{
  "status": "ok"
}
```

## GitHub Actions Deploy

Required repository secrets:

```text
DEPLOY_SSH_KEY
VPS_HOST
VPS_PORT
VPS_USER
API_DOMAIN
SLACK_WEBHOOK_URL   optional
```

Deploy flow:

1. Push or merge to `main`.
2. Tag release if this is a release:

   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. Wait for `Build & Publish Docker Images`.
4. Go to GitHub Actions -> `Deploy to VPS`.
5. Run workflow:
   - `tag`: `v0.1.0` or `dev-test`
   - `environment`: `staging` first, then `production`
   - `skip_backup`: unchecked

The workflow performs:

- pre-deploy backup
- image pull
- `alembic upgrade head`
- rolling restart
- `/health` check
- smoke test
- Docker image cleanup

## Backup Smoke Test

After the stack is running:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production exec backup /usr/local/bin/backup.sh
```

Verify local backup:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production exec backup ls -lh /backups/
```

Verify remote backup:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production exec backup \
  rclone ls b2:smart-dacha-backups-illinci21/postgres/ \
  --config=/etc/rclone/rclone.conf
```

Check Healthchecks.io shows the ping as green.

## Rollback

Fast rollback through GitHub Actions:

1. Open `Deploy to VPS`.
2. Run workflow with the previous known-good tag.
3. Set `skip_backup=true` if the failed deploy may have created data that
   should not be overwritten by another pre-deploy backup.
4. Verify:

   ```bash
   curl -fsS https://api.smartdacha.ua/health | jq .
   ```

Manual rollback on VPS:

```bash
cd /opt/smart-dacha-backend
export RELEASE_TAG=<previous-good-tag>

docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production pull api celery_worker celery_beat backup

docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production run --rm api alembic upgrade head

docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production up -d --no-deps --force-recreate api celery_worker celery_beat backup
```

Database downgrade is not automated. If a migration is not backward-compatible,
restore from backup only after explicit decision.

## Routine Operations

Check service status:

```bash
cd /opt/smart-dacha-backend
docker compose ps
```

Tail logs:

```bash
docker compose logs api --tail=100 -f
docker compose logs celery_worker --tail=100 -f
docker compose logs celery_beat --tail=100 -f
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --profile production logs backup --tail=100 -f
```

Restart API:

```bash
docker compose up -d --no-deps --force-recreate api
```

Disk usage:

```bash
docker system df
df -h
```

Safe image cleanup:

```bash
docker image prune -af --filter "until=72h"
```

## Troubleshooting

### Compose says `POSTGRES_PASSWORD is required`

`.env` is missing or does not contain `POSTGRES_PASSWORD`.

### Compose says `BACKUP_BUCKET is required for backup service`

You loaded `docker-compose.prod.yml` but did not set `BACKUP_BUCKET`.
Set backup env vars or start only base services without the production overlay.

### GHCR pull fails

Run:

```bash
docker login ghcr.io -u illinci21-max
docker pull ghcr.io/illinci21-max/smart-dacha-backend:dev-test
```

For private packages, the token needs package read permission.

### API health check fails

Check:

```bash
docker compose logs api --tail=200
docker compose ps
docker compose exec postgres pg_isready -U smartdacha -d smartdacha
docker compose exec redis redis-cli ping
```

### Migrations fail

Do not continue deploy blindly. Capture:

```bash
docker compose run --rm api alembic current
docker compose run --rm api alembic heads
docker compose run --rm api alembic upgrade head
```

Then decide whether to fix migration code or restore from backup.

## Security Notes

- Keep `.env`, `firebase-credentials.json`, and `secrets/rclone.conf` out of git.
- Use strong generated `POSTGRES_PASSWORD` and `SECRET_KEY`.
- Restrict SSH to key auth when ready.
- Keep ports 5432 and 6379 private; Compose exposes them only inside Docker
  networks by default.
- Backups are compressed PostgreSQL archives, not app-level encrypted archives.
- Rotate GHCR/B2/Healthchecks credentials if they are pasted into an unsafe place.
