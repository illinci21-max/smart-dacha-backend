# CI/CD for Smart Dacha Backend

## Workflows

### `ci.yml` - Continuous Integration

Triggers: push to main/develop, PR, manual.

Runs:

- Ruff linter and format check (informational, will not block)
- Bandit security audit (informational)
- pip-audit CVE scan (informational)
- 143 stable baseline tests with PostgreSQL + Redis services
- Unstable tests (`test_auth.py`, `test_integration.py`) informational only

### `build.yml` - Docker Image Build

Triggers: tag `v*`, manual workflow_dispatch.

Builds and pushes to GHCR:

- `ghcr.io/illinci21-max/smart-dacha-backend:<tag>`
- `ghcr.io/illinci21-max/smart-dacha-backup:<tag>`

Does not auto-deploy.

### `deploy.yml` - Production Deploy

Triggers: manual only.

Inputs:

- `tag` - image tag to deploy
- `environment` - staging or production
- `skip_backup` - emergency rollback only

Steps: pre-deploy backup -> pull -> migrate -> rolling restart -> wait healthy -> smoke tests -> cleanup -> Slack notify.

## Required GitHub Secrets

In Settings -> Secrets and variables -> Actions:

| Name | Required | Purpose |
|------|----------|---------|
| `DEPLOY_SSH_KEY` | yes | Private SSH key (ed25519) for VPS access |
| `VPS_HOST` | yes | VPS IP or domain |
| `VPS_PORT` | yes | SSH port (typically 22) |
| `VPS_USER` | yes | SSH user (typically `deploy`) |
| `API_DOMAIN` | yes | Production API domain (without https://) |
| `SLACK_WEBHOOK_URL` | no | Optional Slack notifications |

## Release Procedure

1. Develop on feature branches -> PR to `main`.
2. CI must pass (lint informational, 143 tests required).
3. Merge PR.
4. Tag release: `git tag v1.0.0 && git push --tags`.
5. `build.yml` builds images automatically.
6. Actions -> Deploy to VPS -> Run workflow:
   - Tag: `v1.0.0`
   - Environment: `staging`
   - Skip backup: unchecked
7. `deploy.yml` pulls GHCR images through `docker-compose.prod.yml`.
8. Verify staging deploy.
9. Re-run with environment: `production`.

## Rollback

If health check fails:

1. Run `deploy.yml` again with previous working tag.
2. Set `skip_backup: true` to preserve any data created during the failed deploy.
3. Verify `/health` returns `ok`.

## Test Debt

`tests/test_auth.py` and `tests/test_integration.py` have pre-existing failures documented in `docs/TEST_DEBT.md`. CI runs them informational only (`continue-on-error: true`). Track separately for cleanup.
