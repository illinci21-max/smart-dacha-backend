"""Celery entry point and scheduled background tasks."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import asyncio
import logging
from uuid import UUID

from celery import Celery
from sqlalchemy import delete, select

from app.config import settings
from app.database import get_sync_session
from app.models import GardenAction, Plot, WeatherDailyCache, WeatherZone
from app.observability import configure_logging, init_sentry
from app.services.redis_service import get_weather_redis_sync
from app.services.sat_service import batch_update_sat_for_zone
from app.services.weather_service import (
    extract_elevation_m,
    fetch_historical_weather_sync,
    fetch_weather_sync,
    is_zone_recently_fetched,
    mark_zone_fetched,
    save_weather_to_db,
)
from app.services.watering_service import batch_generate_watering_recommendations

configure_logging()
init_sentry()
logger = logging.getLogger(__name__)

celery_app = Celery(
    "smartdacha",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_default_queue="default",
    task_routes={
        "weather.*": {"queue": "weather"},
        "sat.*": {"queue": "sat"},
        "watering.*": {"queue": "notifications"},
        "garden_actions.*": {"queue": "default"},
        "plant_profiles.*": {"queue": "default"},
    },
    timezone="Europe/Kyiv",
    enable_utc=True,
    beat_scheduler="redbeat.RedBeatScheduler",
    redbeat_redis_url=settings.REDIS_URL,
    redbeat_lock_timeout=60 * 5,
    beat_schedule={
        "refresh-weather-zones-every-6-hours": {
            "task": "weather.refresh_all_zones",
            "schedule": 6 * 60 * 60,
        },
        "update-sat-daily": {
            "task": "sat.update_all_zones",
            "schedule": 24 * 60 * 60,
            "args": ((date.today() - timedelta(days=1)).isoformat(),),
        },
        "generate-watering-daily": {
            "task": "watering.generate_all_zones",
            "schedule": 24 * 60 * 60,
        },
        "prune-garden-actions-weekly": {
            "task": "garden_actions.prune_old",
            "schedule": 7 * 24 * 60 * 60,
        },
    },
)


def queue_plant_profile_lookup_once(name: str, category: str, ttl_seconds: int = 3600) -> bool:
    normalized = name.strip().lower()
    if not normalized:
        return False
    try:
        redis = get_weather_redis_sync()
        queued = redis.set(f"plant_profile_lookup_queued:{normalized}", "1", ex=ttl_seconds, nx=True)
        if not queued:
            return False
    except Exception as exc:
        logger.warning("Plant profile queue dedup unavailable for %s: %s", name, exc)

    lookup_plant_profile.delay(name, category)
    return True


def queue_weather_refresh_once(zone_id: str, ttl_seconds: int = 120) -> bool:
    """Queue one refresh task per zone within a short Redis TTL window."""
    try:
        redis = get_weather_redis_sync()
        queued = redis.set(f"weather_refresh_queued:{zone_id}", "1", ex=ttl_seconds, nx=True)
        if not queued:
            logger.info("Weather zone %s refresh already queued", zone_id)
            return False
    except Exception as exc:
        logger.warning("Weather queue dedup unavailable for zone %s: %s", zone_id, exc)

    refresh_weather_zone.delay(zone_id)
    return True


@celery_app.task(name="plant_profiles.lookup")
def lookup_plant_profile(name: str, category: str = "Овочі") -> bool:
    async def _run() -> bool:
        from app.database import AsyncSessionLocal
        from app.services.plant_profile_service import lookup_profile

        async with AsyncSessionLocal() as db:
            await lookup_profile(name, category, db, allow_gemini=True)
            await db.commit()
        return True

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.warning("Plant profile background lookup failed for %s: %s", name, exc)
        return False


@celery_app.task(name="system.ping")
def ping() -> dict:
    return {"status": "ok", "app": settings.APP_NAME}


@celery_app.task(name="weather.refresh_zone", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def refresh_weather_zone(zone_id: str) -> int:
    lock_key = f"weather_refresh_running:{zone_id}"
    lock_acquired = False
    try:
        redis = get_weather_redis_sync()
        lock_acquired = bool(redis.set(lock_key, "1", ex=120, nx=True))
    except Exception as exc:
        logger.warning("Weather running lock unavailable for zone %s: %s", zone_id, exc)

    if not lock_acquired:
        logger.info("Weather zone %s skipped: refresh already running", zone_id)
        return 0

    try:
        if is_zone_recently_fetched(zone_id):
            logger.info("Weather zone %s skipped: recently fetched", zone_id)
            return 0

        with get_sync_session() as db:
            zone = db.get(WeatherZone, UUID(zone_id))
            if not zone:
                logger.warning("Weather zone %s not found", zone_id)
                return 0

            plot = db.execute(
                select(Plot).where(
                    Plot.zone_id == zone.id,
                    Plot.latitude.is_not(None),
                    Plot.longitude.is_not(None),
                    Plot.is_deleted.is_(False),
                ).limit(1)
            ).scalar_one_or_none()

            lat = float(plot.latitude) if plot and plot.latitude is not None else float(zone.lat_grid)
            lon = float(plot.longitude) if plot and plot.longitude is not None else float(zone.lon_grid)
            data = fetch_weather_sync(zone_id, lat, lon, zone.timezone or "Europe/Kyiv")
            elevation_m = extract_elevation_m(data)
            if plot and elevation_m is not None and plot.elevation_m is None:
                plot.elevation_m = elevation_m
            saved = save_weather_to_db(zone_id, data, db)

            today = date.today()
            history_start = today - timedelta(days=30)
            history_end = today - timedelta(days=1)
            history_rows = db.execute(
                select(WeatherDailyCache)
                .where(
                    WeatherDailyCache.zone_id == zone.id,
                    WeatherDailyCache.date >= history_start,
                    WeatherDailyCache.date <= history_end,
                )
            ).scalars().all()
            if len(history_rows) < 30:
                history_data = fetch_historical_weather_sync(
                    zone_id,
                    lat,
                    lon,
                    history_start,
                    history_end,
                    zone.timezone or "Europe/Kyiv",
                )
                saved += save_weather_to_db(zone_id, history_data, db)

            mark_zone_fetched(zone_id)
            return saved
    finally:
        if lock_acquired:
            try:
                get_weather_redis_sync().delete(lock_key)
            except Exception as exc:
                logger.warning("Failed to release weather lock zone=%s: %s", zone_id, exc)


@celery_app.task(name="weather.refresh_all_zones")
def refresh_all_weather_zones() -> int:
    queued = 0
    with get_sync_session() as db:
        zone_ids = db.execute(select(WeatherZone.id)).scalars().all()
    for zone_id in zone_ids:
        if queue_weather_refresh_once(str(zone_id)):
            queued += 1
    return queued


@celery_app.task(name="sat.update_zone")
def update_sat_zone(zone_id: str, target_date: str | None = None) -> int:
    day = date.fromisoformat(target_date) if target_date else date.today() - timedelta(days=1)
    with get_sync_session() as db:
        return batch_update_sat_for_zone(zone_id, day, db)


@celery_app.task(name="sat.update_all_zones")
def update_all_sat_zones(target_date: str | None = None) -> int:
    queued = 0
    with get_sync_session() as db:
        zone_ids = db.execute(select(WeatherZone.id)).scalars().all()
    for zone_id in zone_ids:
        update_sat_zone.delay(str(zone_id), target_date)
        queued += 1
    return queued


@celery_app.task(name="watering.generate_zone")
def generate_watering_for_zone(zone_id: str) -> int:
    with get_sync_session() as db:
        return batch_generate_watering_recommendations(zone_id, db)


@celery_app.task(name="watering.generate_all_zones")
def generate_watering_for_all_zones() -> int:
    queued = 0
    with get_sync_session() as db:
        zone_ids = db.execute(select(WeatherZone.id)).scalars().all()
    for zone_id in zone_ids:
        generate_watering_for_zone.delay(str(zone_id))
        queued += 1
    return queued


@celery_app.task(name="garden_actions.prune_old")
def prune_old_garden_actions() -> int:
    retention_days = settings.GARDEN_ACTION_RETENTION_DAYS
    if retention_days <= 0:
        logger.info("Garden action retention disabled")
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    with get_sync_session() as db:
        result = db.execute(delete(GardenAction).where(GardenAction.created_at < cutoff))
        db.commit()
        deleted = result.rowcount or 0
    logger.info("Pruned %d garden actions older than %d days", deleted, retention_days)
    return deleted


app = celery_app
