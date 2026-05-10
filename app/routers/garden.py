"""
Garden Planner Router — уніфікований планувальник грядки.

Повністю відмовляється від хардкоду PLANT_TYPES на користь БД:
  - /plant-types → проксі до plant_profiles + crop_catalog
  - /grid → збереження/завантаження з custom_plants
  - /tasks → FAO-56 розрахунки через AgroTaskEngine

Ендпоінти:
  GET  /garden/plant-types            — каталог із БД (не хардкод!)
  GET  /garden/plots/{id}/grid        — завантажити грядку
  PUT  /garden/plots/{id}/grid        — зберегти грядку + custom_plants
  GET  /garden/plots/{id}/tasks       — FAO-56 завдання
"""
from uuid import UUID
from datetime import date, datetime, timedelta, timezone
import logging
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.plot import Plot
from app.models.plant import Plant
from app.models.plant_profile import PlantProfile
from app.models.crop import CropCatalog
from app.models.weather_cache import WeatherDailyCache
from app.models.garden_action import GardenAction
from app.models.treatment_application import TreatmentApplication
from app.models.garden_observation import GardenObservation
from app.schemas.garden import (
    GardenGridSave,
    GardenGridResponse,
    GardenCellData,
    GardenTasksResponse,
    GardenTaskResponseItem,
    GardenObservationCreate,
    GardenObservationResponse,
)
from app.services.plant_profile_service import lookup_profile
from app.services.sat_service import compute_sat_with_topup
from app.services.smart_gardener_engine import generate_analysis, parse_weather
from app.services.soil_profile_service import PlotOverrides
from app.services.nutrient_ledger_service import nutrient_ledger_from_treatment
from app.services.garden_observation_service import observation_to_engine_payload
from app.services.work_plan_service import dismiss_work_plan_items_not_in_grid, sync_recommendations_to_work_plan
from app.services.weather_service import (
    extract_elevation_m,
    fetch_historical_weather_async,
    fetch_weather_async,
    save_weather_to_db,
)

router = APIRouter(prefix="/garden", tags=["garden"])
logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_plot_or_404(
    plot_id: UUID, user_id, db: AsyncSession
) -> Plot:
    plot = await db.scalar(
        select(Plot).where(
            Plot.id == plot_id,
            Plot.user_id == user_id,
            Plot.is_deleted == False,
        )
    )
    if not plot:
        raise HTTPException(status_code=404, detail="Ділянку не знайдено")
    return plot


def _weather_row_to_dict(row: WeatherDailyCache) -> dict:
    return {
        "date": str(row.date),
        "temp_max": float(row.temp_max) if row.temp_max is not None else None,
        "temp_min": float(row.temp_min) if row.temp_min is not None else None,
        "temp_avg": float(row.temp_avg) if row.temp_avg is not None else None,
        "precipitation": float(row.precipitation) if row.precipitation is not None else None,
        "rain_probability": float(row.rain_probability) if row.rain_probability is not None else None,
        "solar_radiation": float(row.solar_radiation) if row.solar_radiation is not None else None,
        "wind_speed": (float(row.wind_speed) / 3.6) if row.wind_speed is not None else None,
        "wind_height_m": 10,
        "humidity_avg": float(row.humidity_avg) if row.humidity_avg is not None else None,
        "humidity_max": float(row.humidity_max) if row.humidity_max is not None else None,
        "cloud_cover": float(row.cloud_cover) if row.cloud_cover is not None else None,
        "has_dew": row.has_dew,
        "is_fog": row.is_fog,
        "is_forecast": row.is_forecast,
    }




def _queue_weather_refresh(plot: Plot) -> None:
    if not plot.zone_id:
        return
    try:
        from app.workers.celery_app import queue_weather_refresh_once

        queue_weather_refresh_once(str(plot.zone_id))
    except Exception as e:
        logger.warning("Garden tasks weather refresh queue failed for zone %s: %s", plot.zone_id, e)


async def _fetch_weather_now(plot: Plot, db: AsyncSession, *, need_history: bool, need_forecast: bool) -> bool:
    if not plot.zone_id or plot.latitude is None or plot.longitude is None:
        return False
    zone_id = str(plot.zone_id)
    lat = float(plot.latitude)
    lon = float(plot.longitude)
    timezone_str = "Europe/Kyiv"
    saved = 0
    today = date.today()
    try:
        if need_forecast:
            forecast_data = await fetch_weather_async(zone_id, lat, lon, timezone_str)
            elevation_m = extract_elevation_m(forecast_data)
            if elevation_m is not None and plot.elevation_m is None:
                plot.elevation_m = elevation_m
            saved += await db.run_sync(lambda sync_db: save_weather_to_db(zone_id, forecast_data, sync_db))
        if need_history:
            history_data = await fetch_historical_weather_async(
                zone_id,
                lat,
                lon,
                today - timedelta(days=30),
                today - timedelta(days=1),
                timezone_str,
            )
            elevation_m = extract_elevation_m(history_data)
            if elevation_m is not None and plot.elevation_m is None:
                plot.elevation_m = elevation_m
            saved += await db.run_sync(lambda sync_db: save_weather_to_db(zone_id, history_data, sync_db))
        await db.commit()
        logger.info("Garden tasks on-demand weather fetch: plot=%s zone=%s saved=%s", plot.id, zone_id, saved)
        return saved > 0
    except Exception as exc:
        await db.rollback()
        logger.warning("Garden tasks on-demand weather fetch failed for zone %s: %s", zone_id, exc)
        return False


async def _load_weather_context(plot: Plot, db: AsyncSession) -> tuple[dict | None, list[dict], list[dict], str, int | None]:
    if not plot.zone_id:
        return None, [], [], "no_weather_zone", None

    today = date.today()
    history_start = today - timedelta(days=30)
    history_end = today - timedelta(days=1)
    forecast_end = today + timedelta(days=13)

    async def _load_rows():
        result = await db.execute(
            select(WeatherDailyCache)
            .where(
                WeatherDailyCache.zone_id == plot.zone_id,
                WeatherDailyCache.date >= history_start,
                WeatherDailyCache.date <= forecast_end,
            )
            .order_by(WeatherDailyCache.date)
        )
        return result.scalars().all()

    rows = await _load_rows()
    history_count = len([r for r in rows if history_start <= r.date <= history_end])
    forecast_rows = [r for r in rows if today <= r.date <= forecast_end]
    forecast_count = len(forecast_rows)
    if forecast_rows:
        newest_fetch = max((r.fetched_at for r in forecast_rows if r.fetched_at), default=None)
        if newest_fetch:
            if newest_fetch.tzinfo is None:
                newest_fetch = newest_fetch.replace(tzinfo=timezone.utc)
            cache_age = datetime.now(timezone.utc) - newest_fetch
            if cache_age > timedelta(hours=6):
                forecast_count = 0

    today_row = next((r for r in rows if r.date == today), None)
    is_warming = today_row is None or history_count < 7 or forecast_count < 7
    needs_elevation = (
        plot.elevation_m is None
        and plot.latitude is not None
        and plot.longitude is not None
    )

    if history_count < 30 or forecast_count < 14 or needs_elevation:
        fetched = await _fetch_weather_now(
            plot,
            db,
            need_history=history_count < 7,
            need_forecast=today_row is None or forecast_count < 7 or needs_elevation,
        )
        if fetched:
            rows = await _load_rows()
            history_count = len([r for r in rows if history_start <= r.date <= history_end])
            forecast_rows = [r for r in rows if today <= r.date <= forecast_end]
            forecast_count = len(forecast_rows)
            today_row = next((r for r in rows if r.date == today), None)
            is_warming = today_row is None or history_count < 7 or forecast_count < 7
        if history_count < 30 or forecast_count < 14:
            _queue_weather_refresh(plot)

    history = [_weather_row_to_dict(r) for r in rows if r.date < today]
    forecast = [_weather_row_to_dict(r) for r in rows if r.date >= today]
    status = "warming_up" if is_warming else "ready"
    retry_after = 10 if is_warming else None
    return (_weather_row_to_dict(today_row) if today_row else None), forecast, history, status, retry_after

# ══════════════════════════════════════════════════════════════════════════════
# 1. PLANT TYPES — проксі до БД (замість хардкоду PLANT_TYPES)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/plant-types")
async def get_plant_types(
    db: AsyncSession = Depends(get_db),
):
    """
    Повертає каталог рослин із двох джерел:
      1. plant_profiles — агро-профілі (Gemini-generated або вручну)
      2. crop_catalog — системний каталог культур

    Об'єднує дані з дедуплікацією по назві.
    Повертає формат сумісний з Flutter SeedsPanel:
      { "Томат": { "icon": "...", "emoji": "🍅", "category": "Овочі", "varieties": [] } }
    """
    result: dict[str, dict] = {}

    # 1. Профілі з plant_profiles (мають FAO-56 дані)
    profiles = (await db.execute(select(PlantProfile))).scalars().all()
    for p in profiles:
        result[p.name] = {
            "icon": "",
            "emoji": p.emoji or "🌱",
            "category": p.category or "Овочі",
            "varieties": [],
            "has_profile": True,
            "source": p.source or "db",
        }

    # 2. Культури з crop_catalog (системний каталог)
    crops = (await db.execute(select(CropCatalog))).scalars().all()
    for c in crops:
        if c.name_uk not in result:
            result[c.name_uk] = {
                "icon": "",
                "emoji": c.emoji or "🌱",
                "category": c.category or "Овочі",
                "varieties": [],
                "has_profile": False,
                "source": "catalog",
            }

    # Якщо БД порожня — повертаємо базовий набір
    if not result:
        result = _fallback_plant_types()

    logger.debug("plant-types: %d записів (profiles=%d, catalog=%d)",
                 len(result), len(profiles), len(crops))
    return result


def _fallback_plant_types() -> dict:
    """Мінімальний набір коли БД порожня (перший запуск)."""
    return {
        "Томат": {"icon": "", "emoji": "🍅", "category": "Овочі", "varieties": ["Бичаче серце", "Черрі"]},
        "Картопля": {"icon": "", "emoji": "🥔", "category": "Овочі", "varieties": ["Рів'єра"]},
        "Огірок": {"icon": "", "emoji": "🥒", "category": "Овочі", "varieties": ["Маша F1"]},
        "Цибуля": {"icon": "", "emoji": "🧅", "category": "Овочі", "varieties": ["Штутгарт"]},
        "Морква": {"icon": "", "emoji": "🥕", "category": "Овочі", "varieties": ["Нантська"]},
        "Перець": {"icon": "", "emoji": "🌶️", "category": "Овочі", "varieties": ["Калифорнія"]},
        "Капуста": {"icon": "", "emoji": "🥬", "category": "Овочі", "varieties": []},
        "Полуниця": {"icon": "", "emoji": "🍓", "category": "Ягідні кущі", "varieties": []},
        "Укроп": {"icon": "", "emoji": "🌿", "category": "Зелень / Прянощі", "varieties": []},
    }


def _weather_cache_for_sat(weather_today: dict | None, weather_history: list[dict] | None) -> dict[date, object]:
    cache: dict[date, object] = {}
    for payload in [*(weather_history or []), weather_today or {}]:
        raw_date = payload.get("date") if isinstance(payload, dict) else None
        if not raw_date:
            continue
        try:
            cache[date.fromisoformat(str(raw_date)[:10])] = parse_weather(payload)
        except ValueError:
            continue
    return cache


def _sat_profile_from_map(plant_type: str | None, profiles_map: dict[str, dict]) -> SimpleNamespace:
    profile = profiles_map.get(plant_type or "") or {}
    return SimpleNamespace(
        t_base=float(profile.get("t_base") or 10.0),
        t_max_growth=float(profile.get("t_max_growth") or 38.0),
    )


def _plant_match_key(plant_type: str | None, planted_date: object) -> tuple[str, str]:
    return ((plant_type or "").strip().casefold(), str(planted_date or "")[:10])


async def _build_sat_overrides(
    db: AsyncSession,
    plot: Plot,
    cells_raw: list[dict],
    profiles_map: dict[str, dict],
    weather_today: dict | None,
    weather_history: list[dict] | None,
) -> dict[tuple[int, int], float]:
    result = await db.execute(
        select(Plant)
        .where(Plant.plot_id == plot.id, Plant.is_deleted.is_(False))
        .options(selectinload(Plant.crop))
    )
    plants = result.scalars().all()
    if not plants:
        return {}

    today_value = date.today()
    if weather_today and weather_today.get("date"):
        try:
            today_value = date.fromisoformat(str(weather_today["date"])[:10])
        except ValueError:
            pass

    by_id = {str(plant.id): plant for plant in plants}
    by_key: dict[tuple[str, str], list[Plant]] = {}
    for plant in plants:
        crop_name = plant.crop.name_uk if plant.crop else plant.name
        by_key.setdefault(_plant_match_key(crop_name, plant.planted_date), []).append(plant)

    weather_cache = _weather_cache_for_sat(weather_today, weather_history)
    overrides: dict[tuple[int, int], float] = {}
    for cell in cells_raw:
        plant_db = by_id.get(str(cell.get("plant_id") or ""))
        if plant_db is None:
            candidates = by_key.get(_plant_match_key(cell.get("plant_type"), cell.get("planted_date")), [])
            if len(candidates) == 1:
                plant_db = candidates[0]
        if plant_db is None:
            continue
        crop_name = plant_db.crop.name_uk if plant_db.crop else cell.get("plant_type")
        overrides[(int(cell["col"]), int(cell["row"]))] = compute_sat_with_topup(
            plant_db,
            _sat_profile_from_map(crop_name, profiles_map),
            weather_cache,
            today=today_value,
        )
    return overrides


# ══════════════════════════════════════════════════════════════════════════════
# 2. GRID — збереження/завантаження грядки
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/plots/{plot_id}/grid",
    response_model=GardenGridResponse,
)
async def get_garden_grid(
    plot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отримати збережену грядку для ділянки (включаючи кастомні рослини)."""
    plot = await _get_plot_or_404(plot_id, current_user.id, db)
    grid_data = plot.grid_data or {}
    cells_raw = grid_data.get("cells", [])

    return GardenGridResponse(
        plot_id=plot.id,
        cols=grid_data.get("cols", 15),
        rows=grid_data.get("rows", 12),
        cells=[GardenCellData(**c) for c in cells_raw],
        custom_plants=grid_data.get("custom_plants"),
        updated_at=plot.updated_at,
    )


@router.put(
    "/plots/{plot_id}/grid",
    response_model=GardenGridResponse,
)
async def save_garden_grid(
    plot_id: UUID,
    data: GardenGridSave,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Зберегти грядку.
    custom_plants зберігаються в grid_data JSONB як окреме поле —
    це рослини, створені користувачем через SeedsPanel (не з каталогу).
    """
    plot = await _get_plot_or_404(plot_id, current_user.id, db)

    grid_json = {
        "cols": data.cols,
        "rows": data.rows,
        "cells": [c.model_dump() for c in data.cells],
        "custom_plants": data.custom_plants,
    }
    plot.grid_data = grid_json
    flag_modified(plot, "grid_data")
    await dismiss_work_plan_items_not_in_grid(
        db,
        plot_id=plot.id,
        user_id=current_user.id,
        cells=grid_json["cells"],
    )

    await db.commit()
    await db.refresh(plot)

    logger.info(
        "Грядку збережено: plot=%s, %d клітинок, %d кастомних рослин",
        plot_id, len(data.cells),
        len(data.custom_plants) if data.custom_plants else 0,
    )

    return GardenGridResponse(
        plot_id=plot.id,
        cols=data.cols,
        rows=data.rows,
        cells=data.cells,
        custom_plants=data.custom_plants,
        updated_at=plot.updated_at,
    )

@router.get(
    "/plots/{plot_id}/observations",
    response_model=list[GardenObservationResponse],
)
async def get_garden_observations(
    plot_id: UUID,
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plot = await _get_plot_or_404(plot_id, current_user.id, db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)))
    result = await db.execute(
        select(GardenObservation)
        .where(
            GardenObservation.plot_id == plot.id,
            GardenObservation.user_id == current_user.id,
            GardenObservation.observed_at >= cutoff,
        )
        .order_by(GardenObservation.observed_at.desc())
    )
    return [
        GardenObservationResponse(
            id=str(item.id),
            plot_id=item.plot_id,
            scope=item.scope,
            plant_type=item.plant_type,
            variety=item.variety,
            cell_col=item.cell_col,
            cell_row=item.cell_row,
            soil_moisture_pct=item.soil_moisture_pct,
            soil_moisture_status=item.soil_moisture_status,
            leaf_condition=item.leaf_condition,
            symptoms=item.symptoms or [],
            growth_phase=item.growth_phase,
            species_filter=item.species_filter,
            observed_perennial_season=item.observed_perennial_season,
            notes=item.notes,
            observed_at=item.observed_at,
            created_at=item.created_at,
        )
        for item in result.scalars().all()
    ]


@router.post(
    "/plots/{plot_id}/observations",
    response_model=GardenObservationResponse,
)
async def create_garden_observation(
    plot_id: UUID,
    data: GardenObservationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plot = await _get_plot_or_404(plot_id, current_user.id, db)
    symptoms = [str(item).strip() for item in data.symptoms if str(item).strip()]
    species_filter = (
        [str(item).strip() for item in data.species_filter if str(item).strip()]
        if data.species_filter
        else None
    )
    observation = GardenObservation(
        plot_id=plot.id,
        user_id=current_user.id,
        scope=data.scope or "plot",
        plant_type=data.plant_type,
        variety=data.variety,
        cell_col=data.cell_col,
        cell_row=data.cell_row,
        soil_moisture_pct=data.soil_moisture_pct,
        soil_moisture_status=data.soil_moisture_status,
        leaf_condition=data.leaf_condition,
        symptoms=symptoms,
        growth_phase=data.growth_phase,
        species_filter=species_filter,
        observed_perennial_season=data.observed_perennial_season,
        notes=data.notes,
        observed_at=data.observed_at or datetime.now(timezone.utc),
    )
    db.add(observation)
    await db.commit()
    await db.refresh(observation)
    return GardenObservationResponse(
        id=str(observation.id),
        plot_id=observation.plot_id,
        scope=observation.scope,
        plant_type=observation.plant_type,
        variety=observation.variety,
        cell_col=observation.cell_col,
        cell_row=observation.cell_row,
        soil_moisture_pct=observation.soil_moisture_pct,
        soil_moisture_status=observation.soil_moisture_status,
        leaf_condition=observation.leaf_condition,
        symptoms=observation.symptoms or [],
        growth_phase=observation.growth_phase,
        species_filter=observation.species_filter,
        observed_perennial_season=observation.observed_perennial_season,
        notes=observation.notes,
        observed_at=observation.observed_at,
        created_at=observation.created_at,
    )

# ══════════════════════════════════════════════════════════════════════════════
# 3. TASKS — FAO-56 based (замість статичних інтервалів)
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/plots/{plot_id}/tasks",
    response_model=GardenTasksResponse,
)
async def get_garden_tasks(
    plot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Генерує розумні завдання на основі FAO-56 параметрів.

    Для кожної рослини на грядці:
      1. Знаходить PlantProfile (БД → fuzzy → Gemini)
      2. Розраховує поточну фазу росту
      3. Генерує завдання: полив (Kc), підживлення (NPK), захист (sus_*), збирання

    Повертає відсортований за пріоритетом список.
    """
    plot = await _get_plot_or_404(plot_id, current_user.id, db)

    grid_data = plot.grid_data or {}
    cells_raw = grid_data.get("cells", [])
    if not cells_raw:
        return GardenTasksResponse(plot_id=plot.id, tasks=[])

    # Збираємо унікальні назви рослин
    unique_plants = {
        c.get("plant_type", "")
        for c in cells_raw
        if c.get("plant_type")
    }

    # Завантажуємо FAO-56 профілі для кожної рослини
    profiles_map: dict[str, dict] = {}
    gemini_slots = max(0, settings.GEMINI_PROFILE_LOOKUPS_PER_GARDEN_REQUEST)
    for plant_name in unique_plants:
        category = "Овочі"
        # Спробувати знайти категорію з клітинки
        for c in cells_raw:
            if c.get("plant_type") == plant_name and c.get("category"):
                category = c["category"]
                break

        allow_gemini = gemini_slots > 0
        profile_data = await lookup_profile(
            plant_name,
            category,
            db,
            allow_gemini=allow_gemini,
            user_id=current_user.id,
        )
        if profile_data.get("source") == "gemini":
            gemini_slots -= 1
        elif not allow_gemini and profile_data.get("source") == "default":
            try:
                from app.workers.celery_app import queue_plant_profile_lookup_once

                queue_plant_profile_lookup_once(plant_name, category)
            except Exception as exc:
                logger.warning("Plant profile background queue failed for %s: %s", plant_name, exc)
        profiles_map[plant_name] = profile_data

    weather_today, weather_forecast, weather_history, weather_status, retry_after = await _load_weather_context(plot, db)
    if weather_status != "ready":
        return GardenTasksResponse(
            plot_id=plot.id,
            tasks=[],
            status=weather_status,
            retry_after=retry_after,
            weather_status=weather_status,
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=240)
    actions_result = await db.execute(
        select(GardenAction)
        .where(
            GardenAction.plot_id == plot.id,
            GardenAction.user_id == current_user.id,
            GardenAction.created_at >= cutoff,
        )
        .order_by(GardenAction.created_at.desc())
    )
    user_actions = [
        {
            "id": str(action.id),
            "action_type": action.action_type,
            "plant_type": action.plant_type,
            "variety": action.variety,
            "cell_col": action.cell_col,
            "cell_row": action.cell_row,
            "amount": action.amount,
            "notes": action.notes,
            "task_title": action.task_title,
            "scope": action.scope,
            "created_at": action.created_at,
        }
        for action in actions_result.scalars().all()
    ]

    # Генеруємо завдання через backend SmartGardenerEngine.
    action_payloads_by_id = {action["id"]: action for action in user_actions}
    treatments_result = await db.execute(
        select(TreatmentApplication)
        .where(
            TreatmentApplication.plot_id == plot.id,
            TreatmentApplication.user_id == current_user.id,
            TreatmentApplication.applied_at >= cutoff,
        )
        .order_by(TreatmentApplication.applied_at.desc())
    )
    for treatment in treatments_result.scalars().all():
        payload = {
            "treatment_kind": treatment.treatment_kind,
            "target_problem": treatment.target_problem,
            "product_profile_id": treatment.product_profile_id,
            "product_type": treatment.product_type,
            "frac_group": treatment.frac_group,
            "reentry_days": treatment.reentry_days,
            "pre_harvest_interval_days": treatment.pre_harvest_interval_days,
            "rainfast_hours": treatment.rainfast_hours,
        }
        if treatment.treatment_kind == "fertilizer":
            ledger = nutrient_ledger_from_treatment(treatment)
            if not ledger.has_values:
                continue
            payload.update(ledger.to_action_payload())
        if treatment.garden_action_id and str(treatment.garden_action_id) in action_payloads_by_id:
            action_payloads_by_id[str(treatment.garden_action_id)].update(payload)
            continue
        user_actions.append(
            {
                "action_type": "fertilizing" if treatment.treatment_kind == "fertilizer" else "disease",
                "plant_type": treatment.plant_type,
                "variety": treatment.variety,
                "cell_col": treatment.cell_col,
                "cell_row": treatment.cell_row,
                "amount": treatment.applied_amount,
                "notes": treatment.notes,
                "task_title": treatment.product_name,
                "scope": treatment.scope,
                "created_at": treatment.applied_at,
                **payload,
            }
        )

    observations_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    observations_result = await db.execute(
        select(GardenObservation)
        .where(
            GardenObservation.plot_id == plot.id,
            GardenObservation.user_id == current_user.id,
            GardenObservation.observed_at >= observations_cutoff,
        )
        .order_by(GardenObservation.observed_at.desc())
    )
    manual_observations = [
        observation_to_engine_payload(item)
        for item in observations_result.scalars().all()
    ]

    sat_overrides = await _build_sat_overrides(
        db,
        plot,
        cells_raw,
        profiles_map,
        weather_today,
        weather_history,
    )

    analysis = generate_analysis(
        cells_raw,
        profiles_map,
        weather_today=weather_today,
        weather_forecast=weather_forecast,
        weather_history=weather_history,
        user_actions=user_actions,
        manual_observations=manual_observations,
        soil_type=plot.soil_type,
        plot_overrides=PlotOverrides.from_plot(plot),
        latitude=float(plot.latitude) if plot.latitude is not None else None,
        elevation_m=float(plot.elevation_m) if plot.elevation_m is not None else 0.0,
        sat_overrides=sat_overrides,
    )
    await sync_recommendations_to_work_plan(
        db,
        plot_id=plot.id,
        user_id=current_user.id,
        tasks=analysis["tasks"],
        hidden_tasks=analysis.get("hidden_tasks", []),
    )

    return GardenTasksResponse(
        plot_id=plot.id,
        tasks=[GardenTaskResponseItem(**t) for t in analysis["tasks"]],
        hidden_tasks=[GardenTaskResponseItem(**t) for t in analysis.get("hidden_tasks", [])],
        status="ready",
        weather_status="ready",
    )





