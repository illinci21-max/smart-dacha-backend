"""Backend application contract tests.

The old tests in this file targeted a removed Python/Flet API client
(`app.api.client`). The mobile client now lives in Flutter, so these tests
verify backend contracts that the Flutter app depends on.
"""

from app.main import app


def _routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        for method in methods:
            routes.add((method, path))
    return routes


def test_forum_reply_routes_match_flutter_client():
    routes = _routes()

    assert ("GET", "/api/v1/forum/topics/{topic_id}/replies") in routes
    assert ("POST", "/api/v1/forum/topics/{topic_id}/replies") in routes


def test_legacy_forum_reply_route_is_kept_for_compatibility():
    routes = _routes()

    assert ("POST", "/api/v1/forum/topics/{topic_id}/reply") in routes


def test_core_public_routes_are_registered():
    routes = _routes()

    assert ("GET", "/health") in routes
    assert ("POST", "/api/v1/auth/login") in routes
    assert ("POST", "/api/v1/auth/password-reset") in routes
    assert ("POST", "/api/v1/auth/password-reset/confirm") in routes
    assert ("GET", "/api/v1/catalog/crops") in routes
