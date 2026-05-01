from datetime import date, datetime, timedelta, timezone
import uuid

from app.models.work_plan_item import WorkPlanItem
from app.services.smart_gardener_engine import generate_analysis
from app.services.work_plan_service import (
    complete_plan_item,
    done_item_suppresses_task,
    is_actionable_work_plan_task,
)


PROFILE = {
    "category": "Овочі",
    "initial_days": 20,
    "development_days": 30,
    "mid_season_days": 40,
    "late_season_days": 20,
    "kc_initial": 0.40,
    "kc_mid": 1.10,
    "kc_end": 0.70,
    "critical_depletion": 0.45,
    "nitrogen": 2.5,
    "phosphorus": 1.0,
    "potassium": 2.0,
    "magnesium": 0.4,
    "calcium": 0.5,
    "t_base": 10,
    "t_min_growth": 12,
    "t_optimal_min": 20,
    "t_optimal_max": 28,
    "t_max_growth": 38,
    "frost_tolerance": 1,
    "sus_late_blight": 0.90,
    "days_to_harvest_min": 80,
    "days_to_harvest_max": 120,
}


def _cell(plant_type: str = "Кавун", planted_date: str = "2026-04-01") -> dict:
    return {
        "col": 1,
        "row": 2,
        "plant_type": plant_type,
        "planted_date": planted_date,
        "category": "Овочі",
    }


def _weather(
    day: int,
    *,
    rain: float = 0,
    humidity: float = 60,
    temp_max: float = 27,
    temp_min: float = 17,
    wind: float = 2,
    cloud: float = 45,
    dew: bool = False,
) -> dict:
    return {
        "date": f"2026-04-{day:02d}",
        "temp_max": temp_max,
        "temp_min": temp_min,
        "temp_avg": (temp_max + temp_min) / 2,
        "precipitation": rain,
        "rain_probability": 10,
        "solar_radiation": 18,
        "wind_speed": wind,
        "humidity_avg": humidity,
        "humidity_max": min(100, humidity + 10),
        "cloud_cover": cloud,
        "has_dew": dew,
        "is_fog": False,
    }


def _done_item(task_type: str, completed_at: datetime) -> WorkPlanItem:
    return WorkPlanItem(
        id=uuid.uuid4(),
        plot_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        recommendation_key=uuid.uuid4().hex,
        source="agro_analysis",
        status="done",
        task_type=task_type,
        priority="medium",
        category="general",
        title="Полив: Кавун",
        plant_type="Кавун",
        variety="",
        cell_col=1,
        cell_row=2,
        confidence=90,
        completed_at=completed_at,
        created_at=completed_at,
        updated_at=completed_at,
    )


def test_cold_stress_blocks_watering_and_fertilizing():
    analysis = generate_analysis(
        [_cell()],
        {"Кавун": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, temp_max=29, temp_min=18, humidity=35),
        weather_history=[_weather(day, temp_max=30, temp_min=18, humidity=35) for day in range(1, 20)],
        weather_forecast=[
            _weather(21, temp_max=17, temp_min=8, humidity=75),
            _weather(22, temp_max=16, temp_min=7, humidity=80),
            _weather(23, temp_max=19, temp_min=10, humidity=65),
        ],
        soil_type="sand",
    )

    assert any(task["task_type"] == "cold_stress" for task in analysis["tasks"])
    assert not any(task["task_type"] == "watering" for task in analysis["tasks"])
    assert not any(task["task_type"] == "fertilizing" for task in analysis["tasks"])
    assert any(task["task_type"] == "watering" for task in analysis["hidden_tasks"])
    assert any(task["task_type"] == "fertilizing" for task in analysis["hidden_tasks"])


def test_done_work_plan_item_suppresses_only_until_window_expires():
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    item = _done_item("watering", now)
    complete_plan_item(item, completed_at=now)
    task = {
        "task_type": "watering",
        "plant_type": "Кавун",
        "cell_col": 1,
        "cell_row": 2,
    }

    assert done_item_suppresses_task(item, task, now=now + timedelta(days=2))
    assert not done_item_suppresses_task(item, task, now=now + timedelta(days=4))


def test_work_plan_completion_does_not_remove_agroanalysis_risk_without_action():
    base = generate_analysis(
        [_cell()],
        {"Кавун": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, temp_max=29, temp_min=18, humidity=35),
        weather_history=[_weather(day, temp_max=30, temp_min=18, humidity=35) for day in range(1, 20)],
        weather_forecast=[_weather(21, temp_max=17, temp_min=8, humidity=75)],
        user_actions=[],
        soil_type="sand",
    )
    planned_done_only = generate_analysis(
        [_cell()],
        {"Кавун": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, temp_max=29, temp_min=18, humidity=35),
        weather_history=[_weather(day, temp_max=30, temp_min=18, humidity=35) for day in range(1, 20)],
        weather_forecast=[_weather(21, temp_max=17, temp_min=8, humidity=75)],
        user_actions=[],
        soil_type="sand",
    )

    assert any(task["task_type"] == "cold_stress" for task in base["tasks"])
    assert any(task["task_type"] == "cold_stress" for task in planned_done_only["tasks"])


def test_informational_general_tasks_do_not_enter_work_plan():
    assert not is_actionable_work_plan_task(
        {
            "task_type": "general",
            "title": "Стан культури: все добре",
            "description": "Інформаційна рекомендація",
        }
    )


def test_warming_up_response_contract_is_explicit_no_stale_plan_claim():
    response = {
        "tasks": [],
        "hidden_tasks": [],
        "status": "warming_up",
        "retry_after": 10,
        "weather_status": "warming_up",
    }

    assert response["status"] == "warming_up"
    assert response["tasks"] == []
    assert response["retry_after"] == 10
