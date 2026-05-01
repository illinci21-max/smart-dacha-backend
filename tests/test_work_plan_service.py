from datetime import datetime, timedelta, timezone
import uuid

from app.models.work_plan_item import WorkPlanItem
from app.services.work_plan_service import (
    complete_plan_item,
    done_item_suppresses_task,
    suppression_days_for_payload,
    work_plan_item_matches_grid,
)


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
        title="Watering: Watermelon",
        plant_type="Watermelon",
        variety="Crimson",
        cell_col=4,
        cell_row=7,
        confidence=90,
        completed_at=completed_at,
        created_at=completed_at,
        updated_at=completed_at,
    )


def _task(task_type: str) -> dict:
    return {
        "task_type": task_type,
        "plant_type": "Watermelon",
        "variety": "Crimson",
        "cell_col": 4,
        "cell_row": 7,
    }


def test_done_watering_suppresses_recommendation_during_cooldown():
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    item = _done_item("watering", now - timedelta(days=2))

    assert done_item_suppresses_task(item, _task("watering"), now=now)


def test_done_watering_allows_new_recommendation_after_cooldown():
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    item = _done_item("watering", now - timedelta(days=5))

    assert not done_item_suppresses_task(item, _task("watering"), now=now)


def test_done_fertilizing_uses_longer_cooldown():
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    item = _done_item("fertilizing", now - timedelta(days=10))

    assert done_item_suppresses_task(item, _task("fertilizing"), now=now)


def test_complete_plan_item_sets_explicit_suppression_window():
    now = datetime(2026, 4, 29, tzinfo=timezone.utc)
    item = _done_item("watering", now)
    item.status = "planned"
    item.completed_at = None
    item.suppressed_until = None
    item.snoozed_until = now + timedelta(days=1)

    complete_plan_item(item, completed_at=now)

    assert item.status == "done"
    assert item.completed_at == now
    assert item.suppressed_until == now + timedelta(days=3)
    assert item.snoozed_until is None


def test_watering_suppression_uses_soil_etc_rain_and_deficit():
    sand_hot = suppression_days_for_payload(
        "watering",
        reasons=[
            "Полив: дефіцит 78%",
            "Ґрунт: Піщаний (75 мм/м)",
            "ETc: 7 мм/добу",
        ],
    )
    chernozem_mild_with_rain = suppression_days_for_payload(
        "watering",
        reasons=[
            "Полив: дефіцит 30%",
            "Ґрунт: Чорнозем (210 мм/м)",
            "ETc: 3 мм/добу",
            "Дощ завтра: 10 мм",
        ],
    )

    assert sand_hot == 1
    assert chernozem_mild_with_rain == 7


def test_fertilizing_suppression_uses_fertilizer_type_and_leaching():
    foliar = suppression_days_for_payload(
        "fertilizing",
        recommendation_type="листкове",
        reasons=["Ризик вимивання: 20%"],
    )
    organic = suppression_days_for_payload(
        "fertilizing",
        recommendation_type="органіка",
        reasons=["Ризик вимивання: 20%"],
    )
    mineral_after_heavy_rain = suppression_days_for_payload(
        "fertilizing",
        recommendation_type="мінеральне",
        reasons=["Ризик вимивання: 80%", "Дощ за 5 днів: 30 мм"],
    )

    assert foliar < mineral_after_heavy_rain < organic


def test_protection_suppression_uses_min_interval_rei_phi_and_pressure():
    high_pressure = suppression_days_for_payload(
        "disease_protection",
        reasons=["Ризик: 85%", "Тип захисту: контактний фунгіцид"],
        constraints=[
            "re-entry interval 2 дн.",
            "pre-harvest interval 14 дн.",
            "інтервал 10 дн.",
        ],
    )
    low_pressure = suppression_days_for_payload(
        "disease_protection",
        reasons=["Ризик: 45%", "Тип захисту: системний фунгіцид"],
        constraints=[
            "re-entry interval 2 дн.",
            "pre-harvest interval 14 дн.",
            "інтервал 10 дн.",
        ],
    )

    assert high_pressure == 8
    assert low_pressure == 13


def test_planned_item_does_not_match_empty_grid():
    item = _done_item("watering", datetime(2026, 4, 29, tzinfo=timezone.utc))
    item.status = "planned"

    assert not work_plan_item_matches_grid(item, [])


def test_planned_item_matches_only_current_cell_plant():
    item = _done_item("watering", datetime(2026, 4, 29, tzinfo=timezone.utc))
    item.status = "planned"

    assert work_plan_item_matches_grid(
        item,
        [{"col": 4, "row": 7, "plant_type": "Watermelon", "variety": "Crimson"}],
    )
    assert not work_plan_item_matches_grid(
        item,
        [{"col": 4, "row": 7, "plant_type": "Tomato", "variety": ""}],
    )
    assert not work_plan_item_matches_grid(
        item,
        [{"col": 5, "row": 7, "plant_type": "Watermelon", "variety": "Crimson"}],
    )
