"""Sentry, Prometheus, and structured logging setup."""
from __future__ import annotations

import logging
import sys
from typing import Any

import sentry_sdk
from pythonjsonlogger import jsonlogger
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.config import settings

logger = logging.getLogger(__name__)


def _scrub_sensitive_data(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """Remove tokens, passwords, and API keys from Sentry events."""
    request = event.get("request")
    if not isinstance(request, dict):
        return event

    headers = request.get("headers")
    if isinstance(headers, dict):
        sensitive_headers = {"authorization", "cookie", "x-api-key"}
        request["headers"] = {
            key: "[REDACTED]" if key.lower() in sensitive_headers else value
            for key, value in headers.items()
        }

    data = request.get("data")
    if isinstance(data, dict):
        sensitive_keys = {"password", "secret", "token", "api_key"}
        for key in list(data.keys()):
            if key.lower() in sensitive_keys:
                data[key] = "[REDACTED]"

    return event


def init_sentry() -> None:
    """Initialize Sentry SDK if SENTRY_DSN is configured."""
    if not settings.SENTRY_DSN:
        logger.info("Sentry DSN not set, skipping initialization")
        return

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.RELEASE_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
        send_default_pii=False,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
            CeleryIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        before_send=_scrub_sensitive_data,
    )
    logger.info("Sentry initialized for environment=%s", settings.ENVIRONMENT)


def configure_logging() -> None:
    """Set up JSON or text logging based on LOG_FORMAT."""
    handler = logging.StreamHandler(sys.stdout)

    if settings.LOG_FORMAT == "json":
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )

    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
