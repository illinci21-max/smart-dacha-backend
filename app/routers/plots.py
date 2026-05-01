"""
Plots Router — CRUD + weather for user plots.

FIXES from Code Review:
  §4.1 — PaginatedResponse for list endpoint
  §1.4 — weather refresh is queued via Celery instead of HTTP-path fetch
  §5.3 — selectinload to avoid N+1 queries

BUGFIX: replaced str(today) with native date objects in all
        WeatherDailyCache queries. PostgreSQL DATE column cannot
        be compared with VARCHAR — causes UndefinedFunctionError.
"""
from uuid import UUID
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import logging

from app.database import get_db
from app.dependencies import get_current_user, check_plots_limit
from app.models.user import User
from app.models.plot import Plot
from app.models.weather_cache import WeatherDailyCache
from app.schemas.plot import PlotCreate, PlotUpdate, PlotResponse
from app.schemas.pagination import PaginatedResponse, PaginationParams, paginate
from app.services.weather_service import (
    get_or_create_weather_zone,
)
from app.services.fertilizer_profile_service import list_fertilizer_profile_dicts
from app.services.protection_profile_service import list_protection_profile_dicts
from app.services.soil_profile_service import list_soil_profile_dicts

router = APIRouter(prefix="/plots", tags=["plots"])
logger = logging.getLogger(__name__)


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedResponse[PlotResponse])
async def list_plots(
    params: PaginationParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """§4.1 FIX: returns PaginatedResponse instead of bare list."""
    query = (
        select(Plot)
        .where(Plot.user_id == current_user.id, Plot.is_deleted.is_(False))
        .options(selectinload(Plot.plants))   # §5.3: avoid N+1
        .order_by(Plot.created_at.desc())
    )
    return await paginate(db, query, params)


@router.get("/soil-profiles")
async def get_soil_profiles(
    current_user: User = Depends(get_current_user),
):
    """Return supported soil profiles for plot setup and agro-analysis."""
    _ = current_user
    return {"items": list_soil_profile_dicts()}


@router.get("/fertilizer-profiles")
async def get_fertilizer_profiles(
    current_user: User = Depends(get_current_user),
):
    """Return supported fertilizer classes for agro-analysis explanations."""
    _ = current_user
    return {"items": list_fertilizer_profile_dicts()}


@router.get("/protection-profiles")
async def get_protection_profiles(
    current_user: User = Depends(get_current_user),
):
    """Return supported protection classes for disease-risk recommendations."""
    _ = current_user
    return {"items": list_protection_profile_dicts()}


@router.post("", response_model=PlotResponse, status_code=201)
async def create_plot(
    data: PlotCreate,
    current_user: User = Depends(check_plots_limit),
    db: AsyncSession = Depends(get_db),
):
    zone_id = None
    if data.latitude is not None and data.longitude is not None:
        zone_id = await get_or_create_weather_zone(
            float(data.latitude), float(data.longitude), db
        )

    plot_data = data.model_dump()
    plot = Plot(user_id=current_user.id, zone_id=zone_id, **plot_data)
    db.add(plot)
    await db.commit()
    await db.refresh(plot)
    return plot


@router.get("/{plot_id}", response_model=PlotResponse)
async def get_plot(
    plot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plot = await db.scalar(
        select(Plot).where(
            Plot.id == plot_id,
            Plot.user_id == current_user.id,
            Plot.is_deleted.is_(False),
        )
    )
    if not plot:
        raise HTTPException(status_code=404, detail="Ділянку не знайдено")
    return plot


@router.put("/{plot_id}", response_model=PlotResponse)
async def update_plot(
    plot_id: UUID,
    data: PlotUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plot = await db.scalar(
        select(Plot).where(
            Plot.id == plot_id,
            Plot.user_id == current_user.id,
            Plot.is_deleted.is_(False),
        )
    )
    if not plot:
        raise HTTPException(status_code=404, detail="Ділянку не знайдено")

    update_data = data.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(plot, field_name, value)

    # Re-create weather zone if coordinates changed
    if "latitude" in update_data or "longitude" in update_data:
        if "elevation_m" not in update_data:
            plot.elevation_m = None
        if plot.latitude is not None and plot.longitude is not None:
            plot.zone_id = await get_or_create_weather_zone(
                float(plot.latitude), float(plot.longitude), db
            )

    await db.commit()
    await db.refresh(plot)
    return plot


@router.delete("/{plot_id}", status_code=204)
async def delete_plot(
    plot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plot = await db.scalar(
        select(Plot).where(
            Plot.id == plot_id,
            Plot.user_id == current_user.id,
            Plot.is_deleted.is_(False),
        )
    )
    if not plot:
        raise HTTPException(status_code=404, detail="Ділянку не знайдено")

    plot.is_deleted = True
    await db.commit()



def _weather_row_to_dict(row: WeatherDailyCache) -> dict:
    return {
        "date": str(row.date),
        "temp_max": row.temp_max,
        "temp_min": row.temp_min,
        "temp_avg": row.temp_avg,
        "precipitation": row.precipitation,
        "rain_probability": row.rain_probability,
        "solar_radiation": row.solar_radiation,
        "wind_speed": (float(row.wind_speed) / 3.6) if row.wind_speed is not None else None,
        "humidity_avg": row.humidity_avg,
        "humidity_max": row.humidity_max,
        "cloud_cover": row.cloud_cover,
        "has_dew": row.has_dew,
        "is_fog": row.is_fog,
        "is_forecast": row.is_forecast,
    }

# ── Weather ───────────────────────────────────────────────────────────────────

@router.get("/{plot_id}/weather")
async def get_plot_weather(
    plot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current weather for a plot from cache; queues refresh when cache is empty."""
    plot = await db.scalar(
        select(Plot).where(
            Plot.id == plot_id,
            Plot.user_id == current_user.id,
            Plot.is_deleted.is_(False),
        )
    )
    if not plot:
        raise HTTPException(status_code=404, detail="Ділянку не знайдено")

    if not plot.zone_id:
        raise HTTPException(status_code=404, detail="Погодна зона не визначена. Вкажіть координати ділянки.")

    today = date.today()

    # BUGFIX: pass native date object, NOT str(today)
    row = await db.scalar(
        select(WeatherDailyCache).where(
            WeatherDailyCache.zone_id == plot.zone_id,
            WeatherDailyCache.date == today,
        )
    )

    if not row:
        await _on_demand_weather_fetch(plot, db)

    if not row:
        raise HTTPException(status_code=503, detail="Погодні дані тимчасово недоступні")

    return _weather_row_to_dict(row)




@router.get("/{plot_id}/weather/history")
async def get_plot_weather_history(
    plot_id: UUID,
    days: int = Query(30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cached historical daily weather for agro analysis. Returns oldest -> newest."""
    plot = await db.scalar(
        select(Plot).where(
            Plot.id == plot_id,
            Plot.user_id == current_user.id,
            Plot.is_deleted.is_(False),
        )
    )
    if not plot:
        raise HTTPException(status_code=404, detail="Ділянку не знайдено")
    if not plot.zone_id:
        return []

    today = date.today()
    start_date = today - timedelta(days=days)
    end_date = today - timedelta(days=1)

    async def _load_history_rows():
        result = await db.execute(
            select(WeatherDailyCache)
            .where(
                WeatherDailyCache.zone_id == plot.zone_id,
                WeatherDailyCache.date >= start_date,
                WeatherDailyCache.date <= end_date,
            )
            .order_by(WeatherDailyCache.date)
        )
        return result.scalars().all()

    history = await _load_history_rows()

    if len(history) < days and plot.latitude and plot.longitude:
        await _on_demand_weather_fetch(plot, db)

    return [_weather_row_to_dict(r) for r in history]

@router.get("/{plot_id}/forecast")
async def get_plot_forecast(
    plot_id: UUID,
    days: int = Query(7, ge=1, le=14),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plot = await db.scalar(
        select(Plot).where(
            Plot.id == plot_id,
            Plot.user_id == current_user.id,
            Plot.is_deleted.is_(False),
        )
    )
    if not plot:
        raise HTTPException(status_code=404, detail="Ділянку не знайдено")
    if not plot.zone_id:
        return []

    today = date.today()
    end_date = today + timedelta(days=days - 1)

    async def _load_forecast_rows():
        rows = await db.execute(
            select(WeatherDailyCache)
            .where(
                WeatherDailyCache.zone_id == plot.zone_id,
                WeatherDailyCache.date >= today,
                WeatherDailyCache.date <= end_date,
            )
            .order_by(WeatherDailyCache.date)
        )
        return rows.scalars().all()

    forecast = await _load_forecast_rows()

    # Refresh not only when empty, but also when the cached range is incomplete.
    if len(forecast) < days:
        await _on_demand_weather_fetch(plot, db, force=True)

    forecast = forecast[:days]

    return [_weather_row_to_dict(r) for r in forecast]



async def _on_demand_weather_fetch(plot: Plot, db: AsyncSession, force: bool = False) -> None:
    """Queue a Celery refresh; HTTP endpoints must not wait on Open-Meteo."""
    if not plot.zone_id:
        return

    try:
        from app.workers.celery_app import queue_weather_refresh_once

        queue_weather_refresh_once(str(plot.zone_id))
        logger.info("Queued weather refresh for zone %s", plot.zone_id)
    except Exception as e:
        logger.warning("Weather refresh queue failed for zone %s: %s", plot.zone_id, e)
