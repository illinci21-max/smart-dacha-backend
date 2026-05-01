"""
Розумний Дачник — FastAPI Backend Entry Point
Includes: auth, plots, plants, journal, watering, diagnostics,
          catalog, sync, subscriptions, garden, finance, diagnosis_ai, forum,
          biodynamic calendar, plant profiles (AI-powered), garden actions
"""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import async_engine
from app.observability import configure_logging, init_sentry
from app.services.redis_service import RedisManager

from app.routers import (
    auth, plots, plants, journal, watering, diagnostics,
    catalog, sync, subscriptions, garden, finance, diagnosis_ai, forum,
)
from app.routers.biodynamic_router import router as biodynamic_router
from app.routers.plant_profile_router import router as plant_profile_router
from app.routers.garden_actions_router import router as garden_actions_router
from app.routers.work_plan_router import router as work_plan_router
from app.routers.admin import router as admin_router


configure_logging()
init_sentry()
logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s (%s)", settings.APP_NAME, settings.ENVIRONMENT)
    yield
    await async_engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.RELEASE_VERSION,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)

if settings.PROMETHEUS_METRICS_ENABLED:
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/metrics", "/health"],
    ).instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=False,
    )

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    same_site="lax",
    https_only=settings.is_production,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled: %s %s — %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={
        "error": "internal_server_error",
        "message": str(exc) if settings.DEBUG else "Внутрішня помилка",
    })


# ── Register all routers ─────────────────────────────────────────────────────

PREFIX = settings.API_PREFIX
for router_module in [auth, plots, plants, journal, watering, diagnostics,
                      catalog, sync, subscriptions, garden, finance, diagnosis_ai, forum]:
    app.include_router(router_module.router, prefix=PREFIX)

# Biodynamic calendar (Maria Thun)
app.include_router(biodynamic_router, prefix=PREFIX)

# Plant profiles (AI-powered via Gemini)
app.include_router(plant_profile_router, prefix=PREFIX)

# Garden actions history (feedback loop for agro engine)
app.include_router(garden_actions_router, prefix=PREFIX)

# Work plan items (planned recommendations separated from completed actions)
app.include_router(work_plan_router, prefix=PREFIX)

# Internal admin panel (server-rendered web UI)
app.include_router(admin_router)


async def _check_database() -> str:
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        logger.warning("Health database check failed: %s", exc)
        return "fail"


async def _check_redis() -> str:
    try:
        redis = await RedisManager.async_client()
        await redis.ping()
        return "ok"
    except Exception as exc:
        logger.warning("Health redis check failed: %s", exc)
        return "fail"


@app.get("/health", tags=["system"])
async def health():
    return {
        "status": "ok",
        "version": settings.RELEASE_VERSION,
        "environment": settings.ENVIRONMENT,
        "checks": {
            "database": await _check_database(),
            "redis": await _check_redis(),
        },
    }


@app.get("/sentry-debug", include_in_schema=False)
async def sentry_debug():
    if settings.is_production:
        raise HTTPException(status_code=404)
    raise RuntimeError("Sentry test error - this is expected during integration checks")


@app.get("/", include_in_schema=False)
async def root():
    return {"message": f"Welcome to {settings.APP_NAME} API"}
