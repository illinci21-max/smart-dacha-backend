"""
Watering Service — smart irrigation based on Open-Meteo data.

Algorithm (from technical spec):
  Moisture Deficit (DW) — cumulative indicator.
  When DW >= 100 → send push "Plants need watering".

  Step 1: Daily evaporation (E)
    E = Base × K_sun × K_hum
  Step 2: Adjust for rain/fog
  Step 3: Threshold check

FIXES from Code Review:
  §5.2 — uses historical weather from weather_daily_cache for past days
          (was: repeating today's conditions for all days)
  §1.5 — ORM for batch_generate (was: raw SQL)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional
import json
import logging

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ── Algorithm constants ───────────────────────────────────────────────────────
BASE_EVAPORATION = 10.0
DW_WATERING_THRESHOLD = 100.0

K_SUN_CLEAR = 1.5
K_SUN_MIXED = 1.0
K_SUN_CLOUDY = 0.5

K_HUM_DRY = 1.3
K_HUM_NORMAL = 1.0
K_HUM_HUMID = 0.7

RAIN_FACTOR = 15.0
RAIN_THRESHOLD = 0.5
FOG_HUMIDITY = 95.0


@dataclass
class WateringDecision:
    should_water: bool
    amount_ml: int
    urgency: str
    skip_reason: Optional[str]
    dw_value: float = 0.0
    reason_factors: dict = field(default_factory=dict)


def _get_sun_coefficient(cloud_cover_pct: Optional[float], solar_radiation: Optional[float]) -> float:
    if solar_radiation is not None:
        if solar_radiation > 200:
            return K_SUN_CLEAR
        elif solar_radiation > 80:
            return K_SUN_MIXED
        else:
            return K_SUN_CLOUDY
    if cloud_cover_pct is not None:
        if cloud_cover_pct < 25:
            return K_SUN_CLEAR
        elif cloud_cover_pct < 70:
            return K_SUN_MIXED
        else:
            return K_SUN_CLOUDY
    return K_SUN_MIXED


def _get_humidity_coefficient(humidity_pct: Optional[float]) -> float:
    if humidity_pct is None:
        return K_HUM_NORMAL
    if humidity_pct < 40:
        return K_HUM_DRY
    elif humidity_pct <= 70:
        return K_HUM_NORMAL
    else:
        return K_HUM_HUMID


def calculate_daily_evaporation(
    humidity_pct: Optional[float],
    cloud_cover_pct: Optional[float] = None,
    solar_radiation: Optional[float] = None,
    is_fog: bool = False,
) -> float:
    if is_fog:
        return 0.0
    k_sun = _get_sun_coefficient(cloud_cover_pct, solar_radiation)
    k_hum = _get_humidity_coefficient(humidity_pct)
    return BASE_EVAPORATION * k_sun * k_hum


def update_deficit(current_dw: float, evaporation: float, rain_mm: float = 0.0) -> float:
    new_dw = current_dw + evaporation
    if rain_mm > RAIN_THRESHOLD:
        new_dw -= rain_mm * RAIN_FACTOR
    return max(0.0, new_dw)


def calculate_watering_need(
    plant_id: str,
    last_watered_at: Optional[datetime],
    crop: dict,
    weather_today: Optional[dict],
    weather_tomorrow: Optional[dict],
    weather_history: Optional[list[dict]] = None,
) -> WateringDecision:
    """
    Calculate watering need based on DW algorithm.

    §5.2 FIX: added weather_history parameter — list of daily weather dicts
    for past days. If provided, uses actual historical data instead of
    repeating today's conditions.
    """
    base_need_ml: int = crop.get("water_need_ml_per_day") or 300
    drought_tolerance: int = max(1, crop.get("drought_tolerance") or 3)

    if last_watered_at:
        days_dry = max(0, (date.today() - last_watered_at.date()).days)
    else:
        days_dry = 7

    # ── Extract today's weather ───────────────────────────────────────────────
    temp_avg = 20.0
    humidity = 60.0
    rain_mm_today = 0.0
    rain_prob_today = 0.0
    rain_mm_tomorrow = 0.0
    rain_prob_tomorrow = 0.0
    solar_radiation = None
    cloud_cover = None

    if weather_today:
        temp_avg = float(weather_today.get("temp_avg") or 20.0)
        humidity = float(weather_today.get("humidity") or weather_today.get("relative_humidity") or 60.0)
        rain_mm_today = float(weather_today.get("precipitation") or 0.0)
        rain_prob_today = float(weather_today.get("rain_probability") or 0.0)
        solar_radiation = weather_today.get("solar_radiation")
        cloud_cover = weather_today.get("cloud_cover")

    if weather_tomorrow:
        rain_mm_tomorrow = float(weather_tomorrow.get("precipitation") or 0.0)
        rain_prob_tomorrow = float(weather_tomorrow.get("rain_probability") or 0.0)

    is_fog = humidity >= FOG_HUMIDITY and rain_mm_today < 0.1

    # ── Early exit: heavy rain ────────────────────────────────────────────────
    if rain_mm_today > 5 and rain_prob_today > 70:
        return WateringDecision(
            should_water=False, amount_ml=0, urgency="low", dw_value=0.0,
            skip_reason="rain_expected_today",
            reason_factors={"rain_mm_today": rain_mm_today, "rain_probability_today": rain_prob_today},
        )

    # ── §5.2 FIX: Calculate DW using HISTORICAL weather ──────────────────────
    accumulated_dw = 0.0
    history = weather_history or []

    for day_offset in range(days_dry):
        if day_offset < len(history) and history[day_offset]:
            # Use actual historical data for this day
            day_data = history[day_offset]
            day_humidity = float(day_data.get("humidity") or day_data.get("relative_humidity") or humidity)
            day_solar = day_data.get("solar_radiation", solar_radiation)
            day_rain = float(day_data.get("precipitation") or 0.0)
            day_fog = day_humidity >= FOG_HUMIDITY and day_rain < 0.1
        else:
            # Fallback to today's conditions for days without history
            day_humidity = humidity
            day_solar = solar_radiation
            day_rain = rain_mm_today if day_offset == 0 else 0.0
            day_fog = is_fog if day_offset == 0 else False

        daily_evaporation = calculate_daily_evaporation(
            humidity_pct=day_humidity,
            solar_radiation=day_solar,
            is_fog=day_fog,
        )
        accumulated_dw = update_deficit(accumulated_dw, daily_evaporation, day_rain)

    # ── Tomorrow rain penalty ─────────────────────────────────────────────────
    tomorrow_rain_penalty = 0.0
    if rain_mm_tomorrow > 3 and rain_prob_tomorrow > 60:
        tomorrow_rain_penalty = rain_mm_tomorrow * RAIN_FACTOR * 0.5
        accumulated_dw = max(0, accumulated_dw - tomorrow_rain_penalty)

    # ── Urgency ───────────────────────────────────────────────────────────────
    critical_days = drought_tolerance * 2
    high_days = drought_tolerance
    urgency = "low"

    if days_dry >= critical_days or accumulated_dw >= 150:
        urgency = "critical"
    elif days_dry >= high_days or accumulated_dw >= DW_WATERING_THRESHOLD:
        urgency = "high"
    elif temp_avg > 30 or accumulated_dw >= 70:
        urgency = "medium"

    # ── Volume ────────────────────────────────────────────────────────────────
    temp_factor = 1.0 + max(0.0, (temp_avg - 25.0) * 0.1)
    drought_factor = 3.0 / drought_tolerance
    amount_ml = int(base_need_ml * temp_factor * drought_factor * min(days_dry, 7))
    amount_ml = max(100, min(amount_ml, 5000))

    should_water = accumulated_dw >= DW_WATERING_THRESHOLD or days_dry >= high_days

    return WateringDecision(
        should_water=should_water,
        amount_ml=amount_ml if should_water else 0,
        urgency=urgency if should_water else "low",
        dw_value=round(accumulated_dw, 1),
        skip_reason=None if should_water else "moisture_sufficient",
        reason_factors={
            "days_since_last_watering": days_dry,
            "temp_avg": round(temp_avg, 1),
            "humidity_pct": round(humidity, 1),
            "drought_tolerance": drought_tolerance,
            "rain_mm_today": rain_mm_today,
            "rain_mm_tomorrow": rain_mm_tomorrow,
            "accumulated_dw": round(accumulated_dw, 1),
            "dw_threshold": DW_WATERING_THRESHOLD,
            "urgency": urgency,
            "history_days_used": min(len(history), days_dry),
            "history_days_fallback": max(0, days_dry - len(history)),
        },
    )


# ── Batch generation with historical weather (§5.2 + §1.5) ───────────────────

def batch_generate_watering_recommendations(zone_id: str, db_session: Session) -> int:
    """
    Generate watering recommendations for all plants in a zone.
    §5.2 FIX: fetches historical weather from weather_daily_cache.
    §1.5 FIX: uses ORM instead of raw SQL for reads.
    """
    from app.models.plant import Plant
    from app.models.plot import Plot
    from app.models.crop import CropCatalog
    from app.models.weather_cache import WeatherDailyCache
    from app.models.watering import WateringRecommendation
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    today = date.today()
    history_start = today - timedelta(days=30)  # max 30 days of history

    # §1.5: ORM query for plants
    plants = db_session.execute(
        select(
            Plant.id.label("plant_id"),
            Plant.last_watered_at,
            CropCatalog.water_need_ml_per_day,
            CropCatalog.drought_tolerance,
            CropCatalog.t_base,
            Plot.zone_id,
        )
        .join(Plot, Plot.id == Plant.plot_id)
        .join(CropCatalog, CropCatalog.id == Plant.crop_id)
        .where(
            Plot.zone_id == zone_id,
            Plant.is_deleted.is_(False),
            Plot.is_deleted.is_(False),
        )
    ).all()

    # §5.2: Fetch historical weather for the zone (once for all plants)
    weather_rows = db_session.execute(
        select(WeatherDailyCache)
        .where(
            WeatherDailyCache.zone_id == zone_id,
            WeatherDailyCache.date >= history_start,
            WeatherDailyCache.date <= today,
        )
        .order_by(WeatherDailyCache.date.desc())
    ).scalars().all()

    # Build lookup: date_str → weather dict
    weather_by_date: dict[str, dict] = {}
    for w in weather_rows:
        weather_by_date[str(w.date)] = {
            "temp_avg": w.temp_avg,
            "precipitation": w.precipitation,
            "rain_probability": w.rain_probability,
            "solar_radiation": w.solar_radiation,
            "humidity": None,  # Open-Meteo daily doesn't provide humidity
        }

    today_weather = weather_by_date.get(str(today))
    tomorrow_weather = weather_by_date.get(str(today + timedelta(days=1)))

    inserted = 0
    for row in plants:
        try:
            # §5.2: Build historical weather list (most recent day first)
            last_watered = row.last_watered_at
            if last_watered:
                days_dry = max(0, (today - last_watered.date()).days)
            else:
                days_dry = 7

            history = []
            for d in range(days_dry):
                past_date = today - timedelta(days=d)
                day_data = weather_by_date.get(str(past_date))
                history.append(day_data)

            decision = calculate_watering_need(
                plant_id=str(row.plant_id),
                last_watered_at=last_watered,
                crop={
                    "water_need_ml_per_day": row.water_need_ml_per_day,
                    "drought_tolerance": row.drought_tolerance,
                },
                weather_today=today_weather,
                weather_tomorrow=tomorrow_weather,
                weather_history=history,
            )

            if decision.should_water:
                # §1.5: ORM upsert
                stmt = pg_insert(WateringRecommendation).values(
                    plant_id=str(row.plant_id),
                    recommended_date=today,
                    recommended_amount_ml=decision.amount_ml,
                    reason_factors=decision.reason_factors,
                    status="pending",
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["plant_id", "recommended_date"],
                    set_={
                        "recommended_amount_ml": stmt.excluded.recommended_amount_ml,
                        "reason_factors": stmt.excluded.reason_factors,
                    },
                )
                db_session.execute(stmt)
                inserted += 1

        except Exception as e:
            logger.error("Failed to process plant %s: %s", row.plant_id, e)

    db_session.commit()
    logger.info("Generated %d watering recommendations for zone %s", inserted, zone_id)
    return inserted