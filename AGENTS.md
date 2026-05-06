# Codex / AI Agent Instructions

## Stable Test Baseline

Before starting any task, run:

```bash
python -m pytest \
  tests/test_smart_gardener_engine.py \
  tests/test_sat_service.py \
  tests/test_agro_analysis_fixture_scenarios.py \
  tests/test_agro_work_plan_regressions.py \
  tests/test_config_security.py \
  -q
```

This is the stable baseline. It MUST stay green throughout your work.

After observability is added, include `tests/test_observability.py` in the same
baseline.

## Pre-existing Failures

DO NOT fix these as part of unrelated tasks:

- `tests/test_auth.py` — contract drift, see `docs/TEST_DEBT.md`.
- `tests/test_integration.py` — DB fixture issues, see `docs/TEST_DEBT.md`.

If a task is specifically about test stabilization, fix them. Otherwise, leave
them alone.

## Commit Style

Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `ci:`, etc.
One logical change per commit. Show diff before pushing.

## Companion Repos

- Backend (this): github.com/illinci21-max/smart-dacha-backend
- Frontend Flutter app: github.com/illinci21-max/smart-dacha-frontend

Cross-cutting changes require commits in both repos with a cross-reference in
the commit message, for example: `Refs: smart-dacha-frontend@<sha>`.

## After Each Task

1. Run stable baseline; it must stay green.
2. Show file-by-file diff.
3. Show new/changed file list.
4. Wait for human review before the next task.
