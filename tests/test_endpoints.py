"""Endpoint registration tests for the current FastAPI backend."""

from app.main import app


def test_flutter_used_endpoint_groups_are_registered():
    paths = {getattr(route, "path", "") for route in app.routes}

    expected_paths = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/me",
        "/api/v1/plots",
        "/api/v1/plots/{plot_id}/weather",
        "/api/v1/plots/{plot_id}/forecast",
        "/api/v1/plots/{plot_id}/plants",
        "/api/v1/plants/{plant_id}/journal",
        "/api/v1/catalog/crops",
        "/api/v1/watering/today",
        "/api/v1/garden/plots/{plot_id}/grid",
        "/api/v1/finance/transactions",
        "/api/v1/forum/topics",
        "/api/v1/forum/topics/{topic_id}/replies",
        "/api/v1/plant-profiles/lookup",
        "/api/v1/biodynamic/forecast",
    }

    missing = expected_paths - paths
    assert not missing


def test_celery_entrypoint_imports_and_registers_tasks():
    from app.workers.celery_app import celery_app

    assert "weather.refresh_all_zones" in celery_app.tasks
    assert "weather.refresh_zone" in celery_app.tasks
    assert "sat.update_all_zones" in celery_app.tasks
    assert "watering.generate_all_zones" in celery_app.tasks
