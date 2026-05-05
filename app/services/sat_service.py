"""
SAT Service — логіка розрахунку Суми Активних Температур.
Ключова оптимізація: один батч SQL UPDATE на зону замість O(n) запитів на рослину.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
import logging

from app.services.agro_math import calculate_gdd_delta
from app.services.lifecycle_types import LifecycleType

logger = logging.getLogger(__name__)


def calculate_sat_delta(
    temp_avg: float,
    t_base: float,
    temp_min: float | None = None,
    temp_max: float | None = None,
    t_upper: float | None = None,
) -> float:
    """
    САТ-дельта за один день = max(0, T_avg - T_base).
    Якщо середня температура нижча за базову — рослина не розвивається.
    """
    if temp_min is not None and temp_max is not None:
        return calculate_gdd_delta(temp_min, temp_max, t_base, t_upper)
    upper = t_upper if t_upper is not None and t_upper > t_base else None
    capped_avg = min(temp_avg, upper) if upper is not None else temp_avg
    return max(0.0, capped_avg - t_base)


def compute_sat_with_topup(
    plant,
    crop_profile,
    weather_cache: dict[date, object],
    today: date,
    max_topup_days: int = 14,
) -> float:
    """
    Return current SAT from DB baseline plus a small in-memory delta window.

    `plant` is intentionally duck-typed so tests and routers can pass ORM
    objects or light DTOs. Weather items must expose temp_min/temp_max.

    Annual plants are anchored to planted_date. Perennials are anchored to
    January 1 of the current year, because their phenology resets by season,
    not by original planting date.
    """
    try:
        lifecycle = LifecycleType(str(getattr(plant, "lifecycle_type", "annual") or "annual"))
    except ValueError:
        lifecycle = LifecycleType.ANNUAL

    if lifecycle.is_perennial:
        return _compute_sat_perennial(plant, crop_profile, weather_cache, today)
    return _compute_sat_annual(plant, crop_profile, weather_cache, today, max_topup_days)


def _compute_sat_annual(
    plant,
    crop_profile,
    weather_cache: dict[date, object],
    today: date,
    max_topup_days: int = 14,
) -> float:
    """Existing annual SAT logic: DB baseline plus capped top-up window."""
    baseline = float(getattr(plant, "sat_accumulated", None) or 0.0)
    planted_date = getattr(plant, "planted_date", None)
    last_updated = getattr(plant, "sat_last_updated_at", None)
    t_base = float(getattr(crop_profile, "t_base", 10.0) or 10.0)
    t_upper = getattr(crop_profile, "t_max_growth", None)
    if t_upper is not None:
        t_upper = float(t_upper)

    if today is None:
        today = date.today()
    if planted_date and planted_date > today:
        return 0.0

    if last_updated is None or (planted_date and last_updated < planted_date):
        start_day = planted_date or today
        return _compute_sat_delta_range(start_day, today, weather_cache, t_base, t_upper)

    delta_days = (today - last_updated).days
    if delta_days <= 0:
        return baseline
    if delta_days > max_topup_days:
        logger.warning(
            "SAT batch is %d days behind for plant %s; capping topup at %d days",
            delta_days,
            getattr(plant, "id", "<unknown>"),
            max_topup_days,
        )
        delta_days = max_topup_days

    start_day = last_updated + timedelta(days=1)
    end_day = last_updated + timedelta(days=delta_days)
    return baseline + _compute_sat_delta_range(start_day, end_day, weather_cache, t_base, t_upper)


def _compute_sat_perennial(
    plant,
    crop_profile,
    weather_cache: dict[date, object],
    today: date,
) -> float:
    """Compute perennial SAT from Jan 1 of the current calendar year."""
    if today is None:
        today = date.today()

    year_start = date(today.year, 1, 1)
    last_updated = getattr(plant, "sat_last_updated_at", None)
    t_base = float(getattr(crop_profile, "t_base", 10.0) or 10.0)
    t_upper = getattr(crop_profile, "t_max_growth", None)
    if t_upper is not None:
        t_upper = float(t_upper)

    if last_updated is None or last_updated < year_start:
        baseline = 0.0
        topup_start = year_start
    else:
        baseline = float(getattr(plant, "sat_accumulated", None) or 0.0)
        topup_start = last_updated + timedelta(days=1)

    return baseline + _compute_sat_delta_range(
        topup_start,
        today,
        weather_cache,
        t_base,
        t_upper,
    )


def _compute_sat_delta_range(
    start_day: date,
    end_day: date,
    weather_cache: dict[date, object],
    t_base: float,
    t_upper: float | None,
) -> float:
    if start_day > end_day:
        return 0.0
    total = 0.0
    current = start_day
    while current <= end_day:
        weather = weather_cache.get(current)
        if weather is None:
            logger.warning("SAT topup skipped missing weather day %s", current)
        else:
            total += calculate_gdd_delta(
                float(getattr(weather, "temp_min")),
                float(getattr(weather, "temp_max")),
                t_base,
                t_upper,
            )
        current += timedelta(days=1)
    return round(total, 1)


def determine_growth_stage(sat: float, growth_stages: list[dict]) -> Optional[str]:
    """
    Визначає поточну фазу росту рослини за накопиченим САТ.

    growth_stages: [{"name": "сходи", "sat_from": 0, "sat_to": 150}, ...]
    """
    if not growth_stages:
        return None
    for stage in growth_stages:
        if stage.get("sat_from", 0) <= sat <= stage.get("sat_to", float("inf")):
            return stage.get("name")
    # Якщо перевищили всі фази — повертаємо останню
    return growth_stages[-1].get("name") if growth_stages else None


def batch_update_sat_for_zone(zone_id: str, target_date: date, db_session) -> int:
    """
    Один SQL-запит оновлює САТ для ВСІХ рослин у зоні.

    Алгоритм:
    1. Знаходить погоду зони за target_date
    2. Знаходить T_base кожної культури
    3. Рахує delta_sat = max(0, temp_avg - t_base)
    4. Батч-UPDATE plants + оновлення growth_stage

    Повертає кількість оновлених рослин.
    """
    from sqlalchemy import text

    result = db_session.execute(
        text("""
            WITH weather AS (
                SELECT temp_avg, temp_min, temp_max, solar_radiation
                FROM weather_daily_cache
                WHERE zone_id = :zone_id
                  AND date = :target_date
                  AND temp_avg IS NOT NULL
                LIMIT 1
            ),
            plant_deltas AS (
                SELECT
                    pl.id                                           AS plant_id,
                    GREATEST(
                        0,
                        (
                            LEAST(
                                COALESCE(w.temp_max, w.temp_avg),
                                COALESCE(NULLIF(cc.t_optimal_max + 10, 0), 38)
                            )
                            + LEAST(
                                COALESCE(w.temp_min, w.temp_avg),
                                COALESCE(NULLIF(cc.t_optimal_max + 10, 0), 38)
                            )
                        ) / 2 - cc.t_base
                    )                                              AS delta_sat,
                    COALESCE(w.solar_radiation, 0)                 AS delta_insolation,
                    cc.growth_stages                               AS stages
                FROM plants pl
                JOIN plots p   ON p.id   = pl.plot_id
                JOIN crop_catalog cc ON cc.id = pl.crop_id
                CROSS JOIN weather w
                WHERE p.zone_id       = :zone_id
                  AND pl.is_deleted   = FALSE
                  AND p.is_deleted    = FALSE
                  AND (pl.planted_date IS NULL OR pl.planted_date <= :target_date)
            )
            UPDATE plants
            SET
                sat_accumulated          = plants.sat_accumulated + pd.delta_sat,
                sat_last_updated_at      = :target_date,
                insolation_accumulated_wh = plants.insolation_accumulated_wh + pd.delta_insolation,
                updated_at               = NOW()
            FROM plant_deltas pd
            WHERE plants.id = pd.plant_id
            RETURNING plants.id, plants.sat_accumulated, plants.crop_id
        """),
        {"zone_id": zone_id, "target_date": target_date},
    )

    updated_plants = result.fetchall()
    db_session.commit()

    logger.info(
        f"SAT batch update: zone={zone_id}, date={target_date}, "
        f"plants_updated={len(updated_plants)}"
    )
    return len(updated_plants)


def reset_season_sat(zone_id: str, reset_date: date, db_session) -> int:
    """
    Обнуляє САТ на початку нового сезону (1 березня або перший день > 5°C).
    """
    from sqlalchemy import text

    result = db_session.execute(
        text("""
            UPDATE plants
            SET
                sat_accumulated = 0,
                insolation_accumulated_wh = 0,
                sat_reset_date = :reset_date,
                sat_last_updated_at = :reset_date,
                current_growth_stage = NULL,
                updated_at = NOW()
            FROM plots p
            WHERE plants.plot_id = p.id
              AND p.zone_id = :zone_id
              AND plants.is_deleted = FALSE
        """),
        {"zone_id": zone_id, "reset_date": reset_date},
    )
    db_session.commit()
    return result.rowcount
