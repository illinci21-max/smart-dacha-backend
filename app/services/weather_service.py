"""
Weather Service — Open-Meteo API integration with caching.

FIXES from Code Review:
  §1.2 — uses RedisManager instead of local _get_redis()
  §1.4 — added fetch_weather_async() for FastAPI on-demand use
  §1.5 — replaced raw SQL with SQLAlchemy ORM (on_conflict_do_update)
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import settings
from app.models.weather_cache import WeatherDailyCache
from app.models.weather_zone import WeatherZone
from app.services.redis_service import get_weather_redis, get_weather_redis_sync

logger = logging.getLogger(__name__)


def extract_elevation_m(data: dict) -> float | None:
    """Return Open-Meteo response elevation in meters when present."""
    value = data.get("elevation")
    if value is None:
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


# ── Grid coordinates ──────────────────────────────────────────────────────────

def get_grid_coords(lat: float, lon: float) -> tuple[Decimal, Decimal]:
    precision = settings.WEATHER_GRID_PRECISION
    lat_grid = round(Decimal(str(lat)), precision)
    lon_grid = round(Decimal(str(lon)), precision)
    return lat_grid, lon_grid


# ── Weather zone (ORM version — §1.5) ────────────────────────────────────────

async def get_or_create_weather_zone(lat: float, lon: float, db) -> Optional[UUID]:
    """Find or create weather_zone using ORM. Returns zone_id as string."""
    lat_grid, lon_grid = get_grid_coords(lat, lon)

    try:
        # Try to find existing zone
        result = await db.execute(
            select(WeatherZone).where(
                WeatherZone.lat_grid == float(lat_grid),
                WeatherZone.lon_grid == float(lon_grid),
            )
        )
        zone = result.scalar_one_or_none()

        if zone:
            return zone.id

        # Create new zone
        new_zone = WeatherZone(
            lat_grid=float(lat_grid),
            lon_grid=float(lon_grid),
            timezone="Europe/Kyiv",
        )
        db.add(new_zone)
        await db.flush()
        return new_zone.id

    except Exception as e:
        logger.error("Failed to create weather zone: %s", e)
        await db.rollback()
        return None


# ── Async fetch (§1.4 — for FastAPI on-demand) ───────────────────────────────

async def fetch_weather_async(
    zone_id: str,
    lat: float,
    lon: float,
    timezone_str: str = "Europe/Kyiv",
) -> dict:
    """
    Async HTTP request to Open-Meteo /forecast.
    For use in FastAPI endpoints (non-blocking).

    §1.4 FIX: replaces run_in_executor + sync httpx.
    """
    url = f"{settings.OPEN_METEO_BASE_URL}/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "daily": (
            "temperature_2m_max,"
            "temperature_2m_min,"
            "temperature_2m_mean,"
            "precipitation_sum,"
            "precipitation_probability_max,"
            "shortwave_radiation_sum,"
            "weather_code,"
            "relative_humidity_2m_mean,"
            "relative_humidity_2m_max,"
            "cloud_cover_mean,"
            "wind_speed_10m_max"
        ),
        "timezone": timezone_str,
        "forecast_days": 16,
    }

    logger.info("Fetching Open-Meteo async zone=%s lat=%s lon=%s", zone_id, lat, lon)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)
    ) as client:
        response = await client.get(url, params=params)

    if response.status_code != 200:
        body_preview = response.text[:500]
        logger.error("Open-Meteo error: status=%d zone=%s body=%s", response.status_code, zone_id, body_preview)
        raise RuntimeError(f"Open-Meteo returned {response.status_code}")

    data = response.json()
    if "daily" not in data:
        raise RuntimeError(f"Open-Meteo missing 'daily' key: {list(data.keys())}")

    return data



async def fetch_historical_weather_async(
    zone_id: str,
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    timezone_str: str = "Europe/Kyiv",
) -> dict:
    """Fetch historical daily weather from Open-Meteo Archive API."""
    base_url = settings.OPEN_METEO_BASE_URL.replace(
        "api.open-meteo.com", "archive-api.open-meteo.com"
    )
    url = f"{base_url}/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": (
            "temperature_2m_max,"
            "temperature_2m_min,"
            "temperature_2m_mean,"
            "precipitation_sum,"
            "shortwave_radiation_sum,"
            "weather_code,"
            "relative_humidity_2m_mean,"
            "relative_humidity_2m_max,"
            "cloud_cover_mean,"
            "wind_speed_10m_max"
        ),
        "timezone": timezone_str,
    }

    logger.info(
        "Fetching Open-Meteo archive zone=%s lat=%s lon=%s range=%s..%s",
        zone_id, lat, lon, start_date, end_date,
    )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
    ) as client:
        response = await client.get(url, params=params)

    if response.status_code != 200:
        body_preview = response.text[:500]
        logger.error(
            "Open-Meteo archive error: status=%d zone=%s body=%s",
            response.status_code, zone_id, body_preview,
        )
        raise RuntimeError(f"Open-Meteo archive returned {response.status_code}")

    data = response.json()
    if "daily" not in data:
        raise RuntimeError(f"Open-Meteo archive missing 'daily' key: {list(data.keys())}")

    return data

# ── Sync fetch (for Celery workers) ───────────────────────────────────────────

def fetch_weather_sync(
    zone_id: str,
    lat: float,
    lon: float,
    timezone_str: str = "Europe/Kyiv",
) -> dict:
    """Sync HTTP request to Open-Meteo. Used by Celery workers."""
    url = f"{settings.OPEN_METEO_BASE_URL}/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "daily": (
            "temperature_2m_max,"
            "temperature_2m_min,"
            "temperature_2m_mean,"
            "precipitation_sum,"
            "precipitation_probability_max,"
            "shortwave_radiation_sum,"
            "weather_code,"
            "relative_humidity_2m_mean,"
            "relative_humidity_2m_max,"
            "cloud_cover_mean,"
            "wind_speed_10m_max"
        ),
        "timezone": timezone_str,
        "forecast_days": 16,
    }

    logger.info("Fetching Open-Meteo sync zone=%s lat=%s lon=%s", zone_id, lat, lon)

    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0)
        ) as client:
            response = client.get(url, params=params)
    except httpx.TimeoutException as e:
        raise RuntimeError(f"Open-Meteo timeout for zone={zone_id}: {e}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Open-Meteo network error for zone={zone_id}: {e}")

    if response.status_code != 200:
        body_preview = response.text[:500]
        raise RuntimeError(f"Open-Meteo returned {response.status_code}: {body_preview}")

    data = response.json()
    if "daily" not in data:
        raise RuntimeError(f"Open-Meteo missing 'daily' key: {list(data.keys())}")

    logger.info("Open-Meteo success: zone=%s records=%d", zone_id, len(data["daily"].get("time", [])))
    return data


def fetch_historical_weather_sync(
    zone_id: str,
    lat: float,
    lon: float,
    start_date: date,
    end_date: date,
    timezone_str: str = "Europe/Kyiv",
) -> dict:
    """Sync Open-Meteo Archive request for Celery workers."""
    base_url = settings.OPEN_METEO_BASE_URL.replace(
        "api.open-meteo.com", "archive-api.open-meteo.com"
    )
    url = f"{base_url}/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": (
            "temperature_2m_max,"
            "temperature_2m_min,"
            "temperature_2m_mean,"
            "precipitation_sum,"
            "shortwave_radiation_sum,"
            "weather_code,"
            "relative_humidity_2m_mean,"
            "relative_humidity_2m_max,"
            "cloud_cover_mean,"
            "wind_speed_10m_max"
        ),
        "timezone": timezone_str,
    }

    logger.info(
        "Fetching Open-Meteo archive sync zone=%s lat=%s lon=%s range=%s..%s",
        zone_id,
        lat,
        lon,
        start_date,
        end_date,
    )
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
        ) as client:
            response = client.get(url, params=params)
    except httpx.TimeoutException as e:
        raise RuntimeError(f"Open-Meteo archive timeout for zone={zone_id}: {e}")
    except httpx.RequestError as e:
        raise RuntimeError(f"Open-Meteo archive network error for zone={zone_id}: {e}")

    if response.status_code != 200:
        body_preview = response.text[:500]
        raise RuntimeError(f"Open-Meteo archive returned {response.status_code}: {body_preview}")

    data = response.json()
    if "daily" not in data:
        raise RuntimeError(f"Open-Meteo archive missing 'daily' key: {list(data.keys())}")
    return data


# ── Safe float helper ─────────────────────────────────────────────────────────

def _safe_float(value, fallback: float = 0.0) -> float:
    if value is None:
        return fallback
    try:
        result = float(value)
        if result != result or abs(result) == float("inf"):
            return fallback
        return result
    except (TypeError, ValueError):
        return fallback


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _infer_dew(humidity_max: float, precipitation: float, temp_min: float) -> bool:
    return humidity_max >= 95 and precipitation <= 0.5 and temp_min >= -2


# ── Save weather to DB (ORM version — §1.5) ──────────────────────────────────

def save_weather_to_db(zone_id: str, data: dict, db_session) -> int:
    """
    Save daily forecast to weather_daily_cache using ORM.

    §1.5 FIX: replaced raw SQL text() with SQLAlchemy ORM insert...on_conflict.
    """
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    today_date = date.today()
    saved = 0

    if not dates:
        logger.warning("save_weather_to_db: no dates for zone=%s", zone_id)
        return 0

    temp_max_arr = daily.get("temperature_2m_max", [])
    temp_min_arr = daily.get("temperature_2m_min", [])
    temp_avg_arr = daily.get("temperature_2m_mean", [])
    precip_arr = daily.get("precipitation_sum", [])
    rain_prob_arr = daily.get("precipitation_probability_max", [])
    solar_arr = daily.get("shortwave_radiation_sum", [])
    weather_code_arr = daily.get("weather_code", [])
    humidity_avg_arr = daily.get("relative_humidity_2m_mean", [])
    humidity_max_arr = daily.get("relative_humidity_2m_max", [])
    cloud_cover_arr = daily.get("cloud_cover_mean", [])
    wind_arr = daily.get("wind_speed_10m_max", [])

    for i, date_str in enumerate(dates):
        try:
            # Convert API string "2026-03-20" to native date object
            row_date = date.fromisoformat(date_str)

            precipitation = _safe_float(precip_arr[i] if i < len(precip_arr) else None)
            temp_min = _safe_float(temp_min_arr[i] if i < len(temp_min_arr) else None)
            humidity_max = _safe_float(humidity_max_arr[i] if i < len(humidity_max_arr) else None)
            weather_code = _safe_int(weather_code_arr[i] if i < len(weather_code_arr) else None)

            values = {
                "zone_id": zone_id,
                "date": row_date,
                "temp_max": _safe_float(temp_max_arr[i] if i < len(temp_max_arr) else None),
                "temp_min": temp_min,
                "temp_avg": _safe_float(temp_avg_arr[i] if i < len(temp_avg_arr) else None),
                "precipitation": precipitation,
                "rain_probability": _safe_float(rain_prob_arr[i] if i < len(rain_prob_arr) else None),
                "solar_radiation": _safe_float(solar_arr[i] if i < len(solar_arr) else None),
                "wind_speed": _safe_float(wind_arr[i] if i < len(wind_arr) else None),
                "humidity_avg": _safe_float(humidity_avg_arr[i] if i < len(humidity_avg_arr) else None),
                "humidity_max": humidity_max,
                "cloud_cover": _safe_float(cloud_cover_arr[i] if i < len(cloud_cover_arr) else None),
                "has_dew": _infer_dew(humidity_max, precipitation, temp_min),
                "is_fog": weather_code in (45, 48),
                "is_forecast": row_date > today_date,
                "source_api": "open-meteo",
                "fetched_at": datetime.now(timezone.utc),
            }

            stmt = pg_insert(WeatherDailyCache).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["zone_id", "date"],
                set_={
                    "temp_max": stmt.excluded.temp_max,
                    "temp_min": stmt.excluded.temp_min,
                    "temp_avg": stmt.excluded.temp_avg,
                    "precipitation": stmt.excluded.precipitation,
                    "rain_probability": stmt.excluded.rain_probability,
                    "solar_radiation": stmt.excluded.solar_radiation,
                    "wind_speed": stmt.excluded.wind_speed,
                    "humidity_avg": stmt.excluded.humidity_avg,
                    "humidity_max": stmt.excluded.humidity_max,
                    "cloud_cover": stmt.excluded.cloud_cover,
                    "has_dew": stmt.excluded.has_dew,
                    "is_fog": stmt.excluded.is_fog,
                    "is_forecast": stmt.excluded.is_forecast,
                    "source_api": stmt.excluded.source_api,
                    "fetched_at": stmt.excluded.fetched_at,
                },
            )
            db_session.execute(stmt)
            saved += 1
        except Exception as e:
            logger.error("save_weather_to_db: failed date=%s zone=%s: %s", date_str, zone_id, e)

    db_session.commit()
    logger.info("save_weather_to_db: saved %d/%d rows for zone=%s", saved, len(dates), zone_id)
    return saved


# ── Redis cache flags (§1.2 — unified) ───────────────────────────────────────

def is_zone_recently_fetched(zone_id: str) -> bool:
    """Sync check for Celery workers."""
    try:
        r = get_weather_redis_sync()
        return bool(r.get(f"weather_fetch:{zone_id}"))
    except Exception:
        return False


def mark_zone_fetched(zone_id: str) -> None:
    """Sync mark for Celery workers."""
    try:
        r = get_weather_redis_sync()
        r.setex(f"weather_fetch:{zone_id}", settings.WEATHER_CACHE_TTL_SECONDS, "1")
    except Exception as e:
        logger.warning("Failed to mark zone in Redis: %s", e)


async def is_zone_recently_fetched_async(zone_id: str) -> bool:
    """Async check for FastAPI."""
    try:
        r = await get_weather_redis()
        return bool(await r.get(f"weather_fetch:{zone_id}"))
    except Exception:
        return False


async def mark_zone_fetched_async(zone_id: str) -> None:
    """Async mark for FastAPI."""
    try:
        r = await get_weather_redis()
        await r.setex(f"weather_fetch:{zone_id}", settings.WEATHER_CACHE_TTL_SECONDS, "1")
    except Exception as e:
        logger.warning("Failed to mark zone in Redis: %s", e)
