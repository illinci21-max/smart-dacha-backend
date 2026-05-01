# Test Stabilization Backlog

Pre-existing test failures present in the initial commit. These are NOT
blocking production hardening tasks 2-4. Track and fix them in a separate
stabilization sprint.

## Critical (Block CI Before v1.0.0 Release)

### tests/test_auth.py

- **Issue:** `create_token()` tests expect tuple `(token, jti)`, but production
  `create_token()` returns a `str` token only.
- **Issue:** tests import `decode_and_validate_token` from `app.routers.auth`,
  but production code exposes it from `app.dependencies`.
- **Issue:** watering and storage assertions drifted from current production
  service contracts.
- **Fix:** Update tests to current contracts or intentionally change services
  with a dedicated migration.
- **Owner:** TBD
- **Estimate:** 2-4h

### tests/test_integration.py

- **Issue:** Test fixture cannot connect to test DB in the current local Docker
  environment because test database credentials are not aligned.
- **Fix:** Add a proper `.env.test` template, test database bootstrap, and a
  single `TEST_DATABASE_URL` path for local and CI.
- **Owner:** TBD
- **Estimate:** 1-2h

### tests/test_endpoints.py (if applicable)

- **Issue:** TBD.
- **Fix:** TBD.

## Non-critical

- Pydantic v2 class-based config deprecation warnings.
- pytest-asyncio custom `event_loop` fixture deprecation warning.

## Stable Baseline

For tasks 2-4 to proceed, this stable baseline must stay green:

```bash
python -m pytest \
  tests/test_smart_gardener_engine.py \
  tests/test_sat_service.py \
  tests/test_agro_analysis_fixture_scenarios.py \
  tests/test_agro_work_plan_regressions.py \
  tests/test_config_security.py \
  -q
```

Expected result after Task 1: 76 passed.

Never accept a regression in the agro-suite. If the agro-suite breaks, halt.
