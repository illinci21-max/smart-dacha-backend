"""Work plan synchronization for agro-analysis recommendations.

Domain contract:
- Agro-analysis is diagnostic. It shows current risks and may include hidden
  recommendations with explanations, but it does not store user work.
- Work plan is an actionable queue derived from agro-analysis. Completing a
  plan item only means the user cleared that queue item.
- Garden actions are the factual journal. Only actions affect future engine
  cooldowns and treatment/nutrient history.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.garden_action import GardenAction
from app.models.work_plan_item import WorkPlanItem


ACTIONABLE_TASK_TYPES = {
    "watering",
    "fertilizing",
    "disease_protection",
    "pest_control",
    "pruning",
    "harvesting",
    "frost_protection",
    "cold_stress",
}


WORK_PLAN_SUPPRESSION_DAYS = {
    "watering": 3,
    "fertilizing": 14,
    "disease_protection": 10,
    "pest_control": 10,
    "pruning": 14,
    "harvesting": 1,
    "frost_protection": 3,
    "cold_stress": 3,
}


def is_actionable_work_plan_task(task: dict) -> bool:
    task_type = str(task.get("task_type") or "general")
    if task_type not in ACTIONABLE_TASK_TYPES:
        return False
    title = str(task.get("title") or task.get("action") or "").strip()
    return bool(title)


def _norm(value) -> str:
    return str(value or "").strip().casefold()


def task_semantic_key(task: dict) -> str:
    task_type = str(task.get("task_type") or "general")
    return "|".join(
        _norm(value)
        for value in (
            action_type_for_task(task_type),
            task.get("plant_type") or task.get("plant_name"),
            task.get("variety"),
            task.get("cell_col") if task.get("cell_col", -1) != -1 else "",
            task.get("cell_row") if task.get("cell_row", -1) != -1 else "",
        )
    )


def item_semantic_key(item: WorkPlanItem) -> str:
    return "|".join(
        _norm(value)
        for value in (
            action_type_for_task(item.task_type),
            item.plant_type,
            item.variety,
            item.cell_col,
            item.cell_row,
        )
    )


def recommendation_key(task: dict) -> str:
    raw = "|".join(
        str(task.get(key) or "")
        for key in (
            "task_type",
            "plant_type",
            "plant_name",
            "variety",
            "cell_col",
            "cell_row",
            "due_date",
            "action",
            "title",
        )
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def action_type_for_task(task_type: str) -> str:
    return {
        "watering": "watering",
        "fertilizing": "fertilizing",
        "disease_protection": "disease",
        "pest_control": "pest",
        "pruning": "pruning",
        "harvesting": "harvesting",
        "frost_protection": "frost",
        "cold_stress": "frost",
    }.get(task_type, "general")


def suppression_days_for_task(task_type: str) -> int:
    return WORK_PLAN_SUPPRESSION_DAYS.get(str(task_type or "general"), 3)


def _flatten_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(_flatten_values(item))
        return result
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_flatten_values(item))
        return result
    return [str(value)]


def _payload_text(
    *,
    reasons: list | None = None,
    reason_groups: dict | None = None,
    constraints: list | None = None,
    blocked_reasons: list | None = None,
    recommendation_type: str | None = None,
    amount: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> str:
    parts = [
        *(_flatten_values(reasons)),
        *(_flatten_values(reason_groups)),
        *(_flatten_values(constraints)),
        *(_flatten_values(blocked_reasons)),
        recommendation_type or "",
        amount or "",
        title or "",
        description or "",
    ]
    return " ".join(part for part in parts if part).casefold()


def _extract_max_float(text: str, patterns: tuple[str, ...]) -> float | None:
    values: list[float] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            try:
                values.append(float(match.group(1).replace(",", ".")))
            except (ValueError, IndexError):
                continue
    return max(values) if values else None


def _clamp_days(value: float, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(round(value))))


def _watering_suppression_days(text: str) -> int:
    soil_capacity = _extract_max_float(text, (r"(\d+(?:[.,]\d+)?)\s*мм/м",))
    etc_mm = _extract_max_float(text, (r"etc\s*:\s*(\d+(?:[.,]\d+)?)",))
    deficit_pct = _extract_max_float(text, (r"дефіцит[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*%",))
    rain_mm = _extract_max_float(
        text,
        (
            r"дощ[^\d]{0,40}(\d+(?:[.,]\d+)?)\s*мм",
            r"завтра[^\d]{0,60}(\d+(?:[.,]\d+)?)\s*мм",
        ),
    )
    if soil_capacity is None and etc_mm is None and deficit_pct is None and rain_mm is None:
        return suppression_days_for_task("watering")

    days = 2.0
    if soil_capacity is not None:
        if soil_capacity >= 180:
            days += 3
        elif soil_capacity >= 140:
            days += 2
        elif soil_capacity >= 95:
            days += 1

    if etc_mm is not None:
        if etc_mm >= 7:
            days -= 2
        elif etc_mm >= 5:
            days -= 1
        elif etc_mm <= 3:
            days += 1

    if deficit_pct is not None:
        if deficit_pct >= 70:
            days -= 1
        elif deficit_pct <= 35:
            days += 1

    if rain_mm is not None:
        if rain_mm >= 10:
            days += 2
        elif rain_mm >= 5:
            days += 1

    return _clamp_days(days, 1, 7)


def _fertilizing_suppression_days(text: str) -> int:
    rain_mm = _extract_max_float(text, (r"дощ[^\d]{0,40}(\d+(?:[.,]\d+)?)\s*мм", r"опади[^\d]{0,40}(\d+(?:[.,]\d+)?)\s*мм"))
    leaching_pct = _extract_max_float(text, (r"вимиван[^\d]{0,40}(\d+(?:[.,]\d+)?)\s*%",))

    if "органік" in text or "компост" in text or "біогумус" in text:
        days = 21.0
    elif "листков" in text or "по лист" in text:
        days = 7.0
    elif "азот" in text or "nitrogen" in text:
        days = 10.0
    else:
        days = 14.0

    if leaching_pct is not None and leaching_pct >= 70:
        days -= 3
    elif leaching_pct is not None and leaching_pct <= 30:
        days += 2

    if rain_mm is not None and rain_mm >= 25:
        days -= 2

    return _clamp_days(days, 5, 28)


def _protection_suppression_days(text: str) -> int:
    min_interval = _extract_max_float(
        text,
        (
            r"мін\.\s*інтервал\s*(\d+(?:[.,]\d+)?)\s*дн",
            r"мінімальн[^\d]{0,20}інтервал[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*дн",
            r"інтервал\s*(\d+(?:[.,]\d+)?)\s*дн",
            r"min(?:imum)?\s+interval\s*(\d+(?:[.,]\d+)?)\s*дн",
        ),
    )
    rei = _extract_max_float(text, (r"re-?entry interval\s*(\d+(?:[.,]\d+)?)\s*дн", r"\brei\s*:?\s*(\d+(?:[.,]\d+)?)\s*дн"))
    phi = _extract_max_float(text, (r"pre-?harvest interval\s*(\d+(?:[.,]\d+)?)\s*дн", r"\bphi\s*:?\s*(\d+(?:[.,]\d+)?)\s*дн"))
    disease_pressure = _extract_max_float(text, (r"ризик\s*:?\s*(\d+(?:[.,]\d+)?)\s*%",))

    days = min_interval or max(7.0, (phi or 14.0) / 2)
    if rei is not None:
        days = max(days, rei)
    if disease_pressure is not None:
        if disease_pressure >= 80:
            days -= 1
        elif disease_pressure < 55:
            days += 2
    if "системн" in text:
        days += 1
    if "контакт" in text and disease_pressure is not None and disease_pressure >= 70:
        days -= 1

    return _clamp_days(days, 3, 21)


def suppression_days_for_payload(
    task_type: str,
    *,
    reasons: list | None = None,
    reason_groups: dict | None = None,
    constraints: list | None = None,
    blocked_reasons: list | None = None,
    recommendation_type: str | None = None,
    amount: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> int:
    task_type = str(task_type or "general")
    text = _payload_text(
        reasons=reasons,
        reason_groups=reason_groups,
        constraints=constraints,
        blocked_reasons=blocked_reasons,
        recommendation_type=recommendation_type,
        amount=amount,
        title=title,
        description=description,
    )

    if task_type == "watering":
        return _watering_suppression_days(text) if text else suppression_days_for_task(task_type)
    if task_type == "fertilizing":
        return _fertilizing_suppression_days(text) if text else suppression_days_for_task(task_type)
    if task_type in {"disease_protection", "pest_control"}:
        return _protection_suppression_days(text) if text else suppression_days_for_task(task_type)
    return suppression_days_for_task(task_type)


def suppression_until_for_task(
    task_type: str,
    completed_at: datetime,
    **payload,
) -> datetime:
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return completed_at + timedelta(
        days=suppression_days_for_payload(task_type, **payload)
    )


def complete_plan_item(
    item: WorkPlanItem,
    *,
    completed_at: datetime,
    completed_action_id=None,
) -> None:
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    item.status = "done"
    item.completed_action_id = completed_action_id
    item.completed_at = completed_at
    item.suppressed_until = suppression_until_for_task(
        item.task_type,
        completed_at,
        reasons=item.reasons,
        reason_groups=item.reason_groups,
        constraints=item.constraints,
        blocked_reasons=item.blocked_reasons,
        recommendation_type=item.recommendation_type,
        amount=item.amount,
        title=item.title,
        description=item.description,
    )
    item.snoozed_until = None
    item.updated_at = completed_at


def reset_plan_item_for_recommendation(
    item: WorkPlanItem,
    *,
    now: datetime,
    clear_snooze: bool = False,
) -> None:
    item.status = "planned"
    item.completed_at = None
    item.completed_action_id = None
    item.suppressed_until = None
    if clear_snooze:
        item.snoozed_until = None
    item.updated_at = now


def done_item_suppresses_task(
    done_item: WorkPlanItem,
    task: dict,
    *,
    now: datetime | None = None,
) -> bool:
    if item_semantic_key(done_item) != task_semantic_key(task):
        return False

    current_time = now or datetime.now(timezone.utc)
    suppressed_until = done_item.suppressed_until
    if suppressed_until is None and done_item.completed_at is not None:
        suppressed_until = suppression_until_for_task(
            done_item.task_type,
            done_item.completed_at,
            reasons=done_item.reasons,
            reason_groups=done_item.reason_groups,
            constraints=done_item.constraints,
            blocked_reasons=done_item.blocked_reasons,
            recommendation_type=done_item.recommendation_type,
            amount=done_item.amount,
            title=done_item.title,
            description=done_item.description,
        )
    if suppressed_until is None:
        return False
    if suppressed_until.tzinfo is None:
        suppressed_until = suppressed_until.replace(tzinfo=timezone.utc)

    return suppressed_until > current_time


def _item_done_sort_time(item: WorkPlanItem) -> datetime:
    value = item.completed_at or item.updated_at or item.created_at
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _parse_due_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _task_payload(task: dict) -> dict:
    return {
        "task_type": str(task.get("task_type") or "general"),
        "priority": str(task.get("priority") or "medium"),
        "category": str(task.get("category") or "general"),
        "title": str(task.get("title") or task.get("action") or ""),
        "description": task.get("description") or "",
        "amount": task.get("amount") or "",
        "due_date": _parse_due_date(task.get("due_date") or task.get("task_date")),
        "plant_type": task.get("plant_type") or task.get("plant_name"),
        "variety": task.get("variety") or None,
        "cell_col": task.get("cell_col") if task.get("cell_col", -1) != -1 else None,
        "cell_row": task.get("cell_row") if task.get("cell_row", -1) != -1 else None,
        "confidence": int(task.get("confidence") or 80),
        "recommendation_type": task.get("recommendation_type") or "",
        "reasons": task.get("reasons") or [],
        "reason_groups": task.get("reason_groups") or {},
        "constraints": task.get("constraints") or [],
        "blocked_reasons": task.get("blocked_reasons") or [],
        "is_hidden": bool(task.get("is_hidden") or False),
    }


async def sync_recommendations_to_work_plan(
    db: AsyncSession,
    *,
    plot_id: UUID,
    user_id: UUID,
    tasks: list[dict],
    hidden_tasks: list[dict] | None = None,
) -> list[WorkPlanItem]:
    recommendations = [
        task for task in [*tasks, *(hidden_tasks or [])]
        if is_actionable_work_plan_task(task)
    ]
    keys = [recommendation_key(task) for task in recommendations]

    now = datetime.now(timezone.utc)
    planned_result = await db.execute(
        select(WorkPlanItem)
        .where(
            WorkPlanItem.plot_id == plot_id,
            WorkPlanItem.user_id == user_id,
            WorkPlanItem.source == "agro_analysis",
            WorkPlanItem.status == "planned",
        )
    )
    planned_items = planned_result.scalars().all()
    planned_by_key = {item.recommendation_key: item for item in planned_items}

    existing_by_key = dict(planned_by_key)
    done_by_semantic_key: dict[str, WorkPlanItem] = {}
    if keys:
        existing_result = await db.execute(
            select(WorkPlanItem).where(
                WorkPlanItem.plot_id == plot_id,
                WorkPlanItem.user_id == user_id,
                WorkPlanItem.source == "agro_analysis",
                WorkPlanItem.recommendation_key.in_(keys),
            )
        )
        existing_items = existing_result.scalars().all()
        existing_by_key.update(
            {item.recommendation_key: item for item in existing_items}
        )
        for item in existing_items:
            if item.status == "done":
                semantic_key = item_semantic_key(item)
                previous = done_by_semantic_key.get(semantic_key)
                if previous is None or _item_done_sort_time(item) > _item_done_sort_time(previous):
                    done_by_semantic_key[semantic_key] = item

    done_result = await db.execute(
        select(WorkPlanItem).where(
            WorkPlanItem.plot_id == plot_id,
            WorkPlanItem.user_id == user_id,
            WorkPlanItem.source == "agro_analysis",
            WorkPlanItem.status == "done",
        )
    )
    for item in done_result.scalars().all():
        semantic_key = item_semantic_key(item)
        previous = done_by_semantic_key.get(semantic_key)
        if previous is None or _item_done_sort_time(item) > _item_done_sort_time(previous):
            done_by_semantic_key[semantic_key] = item

    for item in planned_items:
        if item.recommendation_key not in keys:
            item.status = "dismissed"
            item.updated_at = now

    synced: list[WorkPlanItem] = []
    for task in recommendations:
        key = recommendation_key(task)
        payload = _task_payload(task)
        item = existing_by_key.get(key)
        if item is not None and item.status == "done":
            if done_item_suppresses_task(item, task, now=now):
                continue
            reset_plan_item_for_recommendation(item, now=now, clear_snooze=True)
            for field_name, value in payload.items():
                setattr(item, field_name, value)
            item.updated_at = now
        elif item is None:
            done_item = done_by_semantic_key.get(task_semantic_key(task))
            if done_item is not None and done_item_suppresses_task(done_item, task, now=now):
                continue
            item = WorkPlanItem(
                plot_id=plot_id,
                user_id=user_id,
                recommendation_key=key,
                source="agro_analysis",
                status="planned",
                **payload,
            )
            db.add(item)
        else:
            reset_plan_item_for_recommendation(item, now=now)
            for field_name, value in payload.items():
                setattr(item, field_name, value)
            item.updated_at = now
        synced.append(item)

    await db.flush()
    return synced


def _grid_cell_key(cell: dict) -> tuple[int | None, int | None]:
    return cell.get("col"), cell.get("row")


def _grid_cell_plant(cell: dict) -> tuple[str, str]:
    return _norm(cell.get("plant_type")), _norm(cell.get("variety"))


def work_plan_item_matches_grid(item: WorkPlanItem, cells: list[dict]) -> bool:
    active_cells = [
        cell for cell in cells
        if _norm(cell.get("plant_type"))
    ]
    if not active_cells:
        return False

    item_plant = _norm(item.plant_type)
    item_variety = _norm(item.variety)
    if item.cell_col is not None and item.cell_row is not None:
        for cell in active_cells:
            if _grid_cell_key(cell) != (item.cell_col, item.cell_row):
                continue
            cell_plant, cell_variety = _grid_cell_plant(cell)
            if item_plant and item_plant != cell_plant:
                return False
            if item_variety and cell_variety and item_variety != cell_variety:
                return False
            return True
        return False

    if not item_plant:
        return True
    return any(item_plant == _grid_cell_plant(cell)[0] for cell in active_cells)


async def dismiss_work_plan_items_not_in_grid(
    db: AsyncSession,
    *,
    plot_id: UUID,
    user_id: UUID,
    cells: list[dict],
) -> int:
    result = await db.execute(
        select(WorkPlanItem).where(
            WorkPlanItem.plot_id == plot_id,
            WorkPlanItem.user_id == user_id,
            WorkPlanItem.source == "agro_analysis",
            WorkPlanItem.status == "planned",
        )
    )
    now = datetime.now(timezone.utc)
    changed = 0
    for item in result.scalars().all():
        if work_plan_item_matches_grid(item, cells):
            continue
        item.status = "dismissed"
        item.updated_at = now
        changed += 1
    if changed:
        await db.flush()
    return changed


async def mark_matching_work_plan_done(
    db: AsyncSession,
    *,
    plot_id: UUID,
    user_id: UUID,
    action: GardenAction,
) -> list[WorkPlanItem]:
    result = await db.execute(
        select(WorkPlanItem)
        .where(
            WorkPlanItem.plot_id == plot_id,
            WorkPlanItem.user_id == user_id,
            WorkPlanItem.status == "planned",
        )
        .order_by(WorkPlanItem.created_at.desc())
    )
    items = result.scalars().all()
    updated_items: list[WorkPlanItem] = []
    now = datetime.now(timezone.utc)
    for item in items:
        if action.task_title and item.title == action.task_title:
            pass
        elif action.action_type != action_type_for_task(item.task_type):
            continue
        elif action.plant_type and item.plant_type and action.plant_type != item.plant_type:
            continue
        elif action.variety and item.variety and action.variety != item.variety:
            continue
        elif action.scope == "single" and action.cell_col is not None and item.cell_col is not None and action.cell_col != item.cell_col:
            continue
        elif action.scope == "single" and action.cell_row is not None and item.cell_row is not None and action.cell_row != item.cell_row:
            continue

        complete_plan_item(
            item,
            completed_at=action.created_at or now,
            completed_action_id=action.id,
        )
        updated_items.append(item)
        if action.scope == "single" or action.task_title:
            break

    await db.flush()
    return updated_items
