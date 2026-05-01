from datetime import date

from app.services.smart_gardener_engine import generate_analysis


PROFILE = {
    "category": "Овочі",
    "initial_days": 10,
    "development_days": 40,
    "mid_season_days": 40,
    "late_season_days": 20,
    "kc_initial": 0.4,
    "kc_mid": 1.1,
    "kc_end": 0.7,
    "sus_late_blight": 0.95,
    "days_to_harvest_min": 90,
    "days_to_harvest_max": 120,
    "t_base": 10,
}


def _wet_weather():
    return {
        "date": "2026-04-29",
        "temp_max": 20,
        "temp_min": 12,
        "temp_avg": 16,
        "precipitation": 3,
        "humidity_avg": 88,
        "humidity_max": 95,
        "wind_speed": 2,
        "cloud_cover": 80,
        "has_dew": True,
    }


def test_recent_protection_suppresses_repeat_disease_task():
    weather = _wet_weather()
    result = generate_analysis(
        [{"col": 1, "row": 1, "plant_type": "Томат", "planted_date": "2026-04-01", "category": "Овочі"}],
        {"Томат": PROFILE},
        today=date(2026, 4, 29),
        weather_today=weather,
        weather_forecast=[weather] * 7,
        weather_history=[weather] * 10,
        user_actions=[
            {
                "action_type": "disease",
                "plant_type": "Томат",
                "cell_col": 1,
                "cell_row": 1,
                "scope": "single",
                "created_at": "2026-04-26T00:00:00+00:00",
                "target_problem": "late_blight",
                "frac_group": "M01",
                "reentry_days": 1,
                "pre_harvest_interval_days": 7,
                "rainfast_hours": 4,
            }
        ],
        soil_type="loam",
    )

    assert not any(task["task_type"] == "disease_protection" for task in result["tasks"])
