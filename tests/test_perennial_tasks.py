"""Tests for perennial-specific fertilizer and protection task generation."""
from __future__ import annotations

from datetime import date, timedelta

from app.services.lifecycle_types import PerennialSeason
from app.services.perennial_phenology import (
    get_perennial_disease_pressure,
    get_perennial_fertilizer_need,
    get_perennial_frost_sensitivity,
)
from app.services.smart_gardener_engine import generate_analysis


APPLE_PROFILE = {
    "kc_initial": 0.45,
    "kc_mid": 1.0,
    "kc_end": 0.7,
    "initial_days": 30,
    "development_days": 30,
    "mid_season_days": 60,
    "late_season_days": 30,
    "root_depth_initial_cm": 30,
    "root_depth_max_cm": 100,
    "field_capacity_mm": 200,
    "wilting_point_mm": 70,
    "critical_depletion": 0.4,
    "t_min_growth": 5,
    "t_optimal_min": 15,
    "t_optimal_max": 25,
    "t_max_growth": 32,
    "t_base": 5,
    "frost_tolerance": -1,
    "nitrogen": 6,
    "phosphorus": 3,
    "potassium": 4,
    "magnesium": 0.5,
    "calcium": 1.5,
    "sus_late_blight": 0,
    "sus_powdery_mildew": 0.3,
    "sus_downy_mildew": 0,
    "sus_botrytis": 0.2,
    "days_to_harvest_min": 120,
    "days_to_harvest_max": 180,
    "profile_confidence": 95,
}


def _weather(day: date, *, temp_min: float = 8, temp_max: float = 19, rain: float = 0) -> dict:
    return {
        "date": day.isoformat(),
        "temp_max": temp_max,
        "temp_min": temp_min,
        "temp_avg": (temp_min + temp_max) / 2,
        "humidity_avg": 60,
        "humidity_max": 80,
        "wind_speed_2m": 2,
        "solar_radiation": 14,
        "precipitation": rain,
        "rain_probability": 0,
        "cloud_cover": 40,
    }


def _history_until(today: date) -> list[dict]:
    start = date(today.year, 1, 1)
    history = []
    for offset in range((today - start).days + 1):
        day = start + timedelta(days=offset)
        if day.month <= 2:
            history.append(_weather(day, temp_min=-2, temp_max=4))
        elif day.month == 3:
            history.append(_weather(day, temp_min=4, temp_max=13))
        else:
            history.append(_weather(day, temp_min=8, temp_max=19))
    return history


def _apple_cell(*, planting_year: int = 2022) -> dict:
    return {
        "col": 0,
        "row": 0,
        "plant_type": "Яблуня",
        "category": "Дерева",
        "planted_date": f"{planting_year}-04-01",
        "lifecycle_type": "perennial_woody_deciduous",
        "planting_year": planting_year,
    }


class TestFertilizerNeeds:
    def test_dormant_winter_no_needs(self):
        assert get_perennial_fertilizer_need(PerennialSeason.DORMANT_WINTER) == {}

    def test_bud_break_has_boron_zinc(self):
        needs = get_perennial_fertilizer_need(PerennialSeason.BUD_BREAK)
        assert "boron" in needs
        assert "zinc" in needs
        assert needs["nitrogen"] >= 5

    def test_flowering_has_high_boron(self):
        needs = get_perennial_fertilizer_need(PerennialSeason.FLOWERING_FRUIT_SET)
        assert needs["boron"] >= 0.05

    def test_harvest_no_nitrogen(self):
        needs = get_perennial_fertilizer_need(PerennialSeason.HARVEST_RIPENING)
        assert needs.get("nitrogen", 0) == 0


class TestFrostSensitivity:
    def test_flowering_is_most_sensitive(self):
        assert get_perennial_frost_sensitivity(PerennialSeason.FLOWERING_FRUIT_SET) > 0.9

    def test_dormancy_is_least_sensitive(self):
        assert get_perennial_frost_sensitivity(PerennialSeason.DORMANT_WINTER) < 0.1


class TestDiseasePressure:
    def test_flowering_has_peak_apple_scab_pressure(self):
        pressure = get_perennial_disease_pressure(PerennialSeason.FLOWERING_FRUIT_SET)
        assert pressure["apple_scab"] >= 0.8

    def test_dormant_winter_has_no_disease_pressure(self):
        assert get_perennial_disease_pressure(PerennialSeason.DORMANT_WINTER) == {}


class TestEngineGeneratesPerennialTasks:
    def test_mature_apple_in_april_gets_micronutrient_task(self):
        today = date(2026, 4, 25)
        history = _history_until(today)

        result = generate_analysis(
            [_apple_cell()],
            {"Яблуня": APPLE_PROFILE},
            today=today,
            weather_today=history[-1],
            weather_forecast=[_weather(today + timedelta(days=1))],
            weather_history=history,
            soil_type="loam",
            latitude=50.45,
            elevation_m=180,
        )

        fert_tasks = [task for task in result["tasks"] if task["task_type"] == "fertilizing"]
        assert any(task["recommendation_type"] == "perennial_micronutrient_foliar" for task in fert_tasks)
        all_reasons = " ".join(reason for task in fert_tasks for reason in task.get("reasons", []))
        assert "розпускання бруньок" in all_reasons

    def test_mature_apple_in_may_gets_scab_protection_task(self):
        today = date(2026, 5, 15)
        history = _history_until(today)

        result = generate_analysis(
            [_apple_cell()],
            {"Яблуня": APPLE_PROFILE},
            today=today,
            weather_today=history[-1],
            weather_forecast=[_weather(today + timedelta(days=1))],
            weather_history=history,
            soil_type="loam",
            latitude=50.45,
            elevation_m=180,
        )

        protection_tasks = [task for task in result["tasks"] if task["task_type"] == "disease_protection"]
        assert any("apple_scab" in task["recommendation_type"] for task in protection_tasks)

    def test_apple_during_flowering_with_frost_forecast_gets_warning(self):
        today = date(2026, 5, 15)
        history = _history_until(today)

        result = generate_analysis(
            [_apple_cell()],
            {"Яблуня": APPLE_PROFILE},
            today=today,
            weather_today=history[-1],
            weather_forecast=[
                _weather(today + timedelta(days=1), temp_min=-3, temp_max=7),
                _weather(today + timedelta(days=2), temp_min=4, temp_max=14),
            ],
            weather_history=history,
            soil_type="loam",
            latitude=50.45,
            elevation_m=180,
        )

        frost_tasks = [task for task in result["tasks"] if task["task_type"] == "frost_protection"]
        assert any(task["priority"] == "high" for task in frost_tasks)
        assert any(task["recommendation_type"] == "perennial_frost_protection" for task in frost_tasks)
