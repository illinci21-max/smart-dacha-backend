from datetime import date

from app.services.smart_gardener_engine import generate_analysis, generate_tasks


BASE_PROFILE = {
    "initial_days": 25,
    "development_days": 35,
    "mid_season_days": 40,
    "late_season_days": 25,
    "kc_initial": 0.40,
    "kc_mid": 1.15,
    "kc_end": 0.70,
    "root_depth_initial_cm": 10,
    "root_depth_max_cm": 70,
    "critical_depletion": 0.50,
    "nitrogen": 2.5,
    "phosphorus": 1.0,
    "potassium": 2.0,
    "magnesium": 0.4,
    "calcium": 0.5,
    "t_base": 10,
    "t_min_growth": 8,
    "t_optimal_min": 18,
    "t_optimal_max": 28,
    "t_max_growth": 38,
    "frost_tolerance": 1,
    "sus_late_blight": 0.85,
    "sus_powdery_mildew": 0.3,
    "sus_downy_mildew": 0.3,
    "sus_botrytis": 0.3,
    "days_to_harvest_min": 70,
    "days_to_harvest_max": 120,
    "profile_confidence": 95,
}


def weather(
    day: int,
    *,
    rain: float = 0,
    rain_probability: float = 10,
    humidity: float = 65,
    temp_max: float = 26,
    temp_min: float = 16,
    wind: float = 2,
    cloud: float = 45,
    dew: bool = False,
    fog: bool = False,
):
    return {
        "date": f"2026-04-{day:02d}",
        "temp_max": temp_max,
        "temp_min": temp_min,
        "temp_avg": (temp_max + temp_min) / 2,
        "precipitation": rain,
        "rain_probability": rain_probability,
        "solar_radiation": 18,
        "wind_speed": wind,
        "humidity_avg": humidity,
        "humidity_max": min(100, humidity + 10),
        "cloud_cover": cloud,
        "has_dew": dew,
        "is_fog": fog,
    }


def cell(plant_type: str, planted_date: str, *, variety: str = ""):
    return {
        "col": 1,
        "row": 2,
        "plant_type": plant_type,
        "variety": variety,
        "planted_date": planted_date,
        "category": "Овочі",
    }


def test_fixture_watermelon_cold_stress_before_frost():
    watermelon = {
        **BASE_PROFILE,
        "t_min_growth": 12,
        "t_optimal_min": 20,
        "frost_tolerance": 2,
        "days_to_harvest_min": 80,
        "days_to_harvest_max": 110,
    }

    tasks = generate_tasks(
        [cell("Watermelon", "2026-04-10")],
        {"Watermelon": watermelon},
        today=date(2026, 4, 20),
        weather_today=weather(20, temp_max=19, temp_min=12),
        weather_forecast=[
            weather(21, temp_max=17, temp_min=10),
            weather(22, temp_max=16, temp_min=9),
            weather(23, temp_max=18, temp_min=11),
        ],
        soil_type="loam",
    )

    cold = next(t for t in tasks if t["task_type"] == "cold_stress")
    assert cold["priority"] in {"high", "critical"}
    assert cold["due_date"] in {"2026-04-21", "2026-04-22"}
    assert cold["reason_groups"].get("weather")


def test_fixture_tomato_four_humid_days_triggers_late_blight_protection():
    tomato = {**BASE_PROFILE, "sus_late_blight": 0.95}
    humid = {
        "rain": 2,
        "rain_probability": 80,
        "humidity": 88,
        "temp_max": 22,
        "temp_min": 14,
        "cloud": 80,
        "dew": True,
    }

    tasks = generate_tasks(
        [cell("Tomato", "2026-03-01")],
        {"Tomato": tomato},
        today=date(2026, 4, 20),
        weather_today=weather(20, **humid),
        weather_history=[weather(day, **humid) for day in range(16, 20)],
        weather_forecast=[weather(21, **humid), weather(22, **humid), weather(23, rain=0, humidity=80)],
        soil_type="clay",
    )

    protection = next(t for t in tasks if t["task_type"] == "disease_protection")
    assert protection["recommendation_type"] == "системний фунгіцид"
    assert protection["reason_groups"].get("protection")
    assert any(item.startswith("FRAC ") for item in protection["constraints"])


def test_fixture_sand_heat_triggers_watering():
    tasks = generate_tasks(
        [cell("Tomato", "2026-03-01")],
        {"Tomato": BASE_PROFILE},
        today=date(2026, 4, 20),
        weather_today=weather(20, temp_max=34, temp_min=20, humidity=35),
        weather_history=[
            weather(day, temp_max=34, temp_min=20, humidity=35)
            for day in range(1, 20)
        ],
        weather_forecast=[weather(21, temp_max=31, temp_min=19, humidity=40)],
        soil_type="sand",
    )

    watering = next(t for t in tasks if t["task_type"] == "watering")
    assert watering["priority"] in {"medium", "high", "critical"}
    assert watering["reason_groups"].get("soil")
    assert "л" in watering["amount"]


def test_fixture_fertilizing_hidden_before_strong_rain():
    analysis = generate_analysis(
        [cell("Tomato", "2026-04-01")],
        {"Tomato": BASE_PROFILE},
        today=date(2026, 4, 20),
        weather_today=weather(20, temp_max=24, temp_min=15),
        weather_history=[weather(day, temp_max=24, temp_min=15) for day in range(1, 20)],
        weather_forecast=[
            weather(21, rain=12, rain_probability=90, humidity=88),
            weather(22, rain=3, rain_probability=70),
            weather(23),
        ],
        soil_type="loam",
    )

    assert not any(t["task_type"] == "fertilizing" for t in analysis["tasks"])
    hidden = next(t for t in analysis["hidden_tasks"] if t["task_type"] == "fertilizing")
    assert hidden["is_hidden"] is True
    assert hidden["blocked_reasons"]


def test_fixture_cold_stress_hides_watering_and_fertilizing():
    cold_sensitive = {
        **BASE_PROFILE,
        "t_min_growth": 12,
        "t_optimal_min": 20,
        "critical_depletion": 0.45,
    }

    analysis = generate_analysis(
        [cell("Watermelon", "2026-04-01")],
        {"Watermelon": cold_sensitive},
        today=date(2026, 4, 20),
        weather_today=weather(20, temp_max=27, temp_min=17, humidity=35),
        weather_history=[
            weather(day, temp_max=30, temp_min=18, humidity=30)
            for day in range(1, 20)
        ],
        weather_forecast=[
            weather(21, temp_max=17, temp_min=8, humidity=70),
            weather(22, temp_max=16, temp_min=7, humidity=75),
            weather(23, temp_max=19, temp_min=10, humidity=65),
        ],
        soil_type="sand",
    )

    assert any(t["task_type"] == "cold_stress" for t in analysis["tasks"])
    assert not any(t["task_type"] == "watering" for t in analysis["tasks"])
    assert not any(t["task_type"] == "fertilizing" for t in analysis["tasks"])

    hidden_watering = next(t for t in analysis["hidden_tasks"] if t["task_type"] == "watering")
    hidden_fertilizing = next(t for t in analysis["hidden_tasks"] if t["task_type"] == "fertilizing")
    assert hidden_watering["is_hidden"] is True
    assert hidden_fertilizing["is_hidden"] is True
    assert hidden_watering["blocked_reasons"]
    assert hidden_fertilizing["blocked_reasons"]


def test_fixture_fungicide_hidden_by_pre_harvest_interval():
    near_harvest = {
        **BASE_PROFILE,
        "days_to_harvest_min": 55,
        "days_to_harvest_max": 90,
        "sus_late_blight": 0.95,
    }
    humid = {
        "rain": 2,
        "rain_probability": 80,
        "humidity": 88,
        "temp_max": 22,
        "temp_min": 14,
        "cloud": 80,
        "dew": True,
    }

    analysis = generate_analysis(
        [cell("Tomato", "2026-03-01")],
        {"Tomato": near_harvest},
        today=date(2026, 4, 20),
        weather_today=weather(20, **humid),
        weather_history=[weather(day, **humid) for day in range(13, 20)],
        weather_forecast=[weather(21, **humid), weather(22, **humid)],
        soil_type="clay",
    )

    assert not any(t["task_type"] == "disease_protection" for t in analysis["tasks"])
    hidden = next(t for t in analysis["hidden_tasks"] if t["task_type"] == "disease_protection")
    assert hidden["is_hidden"] is True
    assert any("pre-harvest interval" in item for item in hidden["constraints"])
    assert hidden["blocked_reasons"]
