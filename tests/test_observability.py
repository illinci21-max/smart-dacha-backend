from fastapi.testclient import TestClient

from app import observability
from app.main import app


def test_sentry_skipped_when_no_dsn(monkeypatch):
    monkeypatch.setattr(observability.settings, "SENTRY_DSN", None)

    observability.init_sentry()


def test_scrub_sensitive_data_removes_authorization_header():
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer secret-token",
                "Content-Type": "application/json",
            }
        }
    }

    scrubbed = observability._scrub_sensitive_data(event)

    assert scrubbed["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert scrubbed["request"]["headers"]["Content-Type"] == "application/json"


def test_scrub_sensitive_data_removes_password_field():
    event = {
        "request": {
            "data": {
                "email": "user@example.com",
                "password": "secret-password",
            }
        }
    }

    scrubbed = observability._scrub_sensitive_data(event)

    assert scrubbed["request"]["data"]["password"] == "[REDACTED]"
    assert scrubbed["request"]["data"]["email"] == "user@example.com"


def test_health_endpoint_returns_environment_and_version(monkeypatch):
    import app.main as main

    async def ok_check():
        return "ok"

    monkeypatch.setattr(main, "_check_database", ok_check)
    monkeypatch.setattr(main, "_check_redis", ok_check)

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == main.settings.RELEASE_VERSION
    assert body["environment"] == main.settings.ENVIRONMENT
    assert body["checks"] == {"database": "ok", "redis": "ok"}


def test_metrics_endpoint_responds():
    response = TestClient(app).get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "# HELP" in response.text


def test_sentry_debug_returns_404_in_production(monkeypatch):
    import app.main as main

    monkeypatch.setattr(main.settings, "ENVIRONMENT", "production")

    response = TestClient(app).get("/sentry-debug")

    assert response.status_code == 404
