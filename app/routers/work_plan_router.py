"""Work plan API: planned recommendations separated from completed actions."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.garden_action import GardenAction
from app.models.plot import Plot
from app.models.user import User
from app.models.work_plan_item import WorkPlanItem
from app.schemas.garden import WorkPlanCompleteAction, WorkPlanItemResponse, WorkPlanItemUpdate
from app.services.treatment_application_service import ensure_treatment_for_action
from app.services.work_plan_service import action_type_for_task, complete_plan_item, dismiss_work_plan_items_not_in_grid

router = APIRouter(prefix="/garden", tags=["work-plan"])


async def _get_plot(plot_id: UUID, user_id, db: AsyncSession) -> Plot:
    plot = await db.scalar(
        select(Plot).where(
            Plot.id == plot_id,
            Plot.user_id == user_id,
            Plot.is_deleted.is_(False),
        )
    )
    if not plot:
        raise HTTPException(404, "Ділянку не знайдено")
    return plot


def _to_response(item: WorkPlanItem) -> WorkPlanItemResponse:
    return WorkPlanItemResponse(
        id=str(item.id),
        plot_id=item.plot_id,
        recommendation_key=item.recommendation_key,
        source=item.source,
        status=item.status,
        task_type=item.task_type,
        priority=item.priority,
        category=item.category,
        title=item.title,
        description=item.description or "",
        amount=item.amount or "",
        due_date=item.due_date.isoformat() if item.due_date else None,
        plant_type=item.plant_type,
        variety=item.variety,
        cell_col=item.cell_col,
        cell_row=item.cell_row,
        confidence=item.confidence,
        recommendation_type=item.recommendation_type or "",
        reasons=item.reasons or [],
        reason_groups=item.reason_groups or {},
        constraints=item.constraints or [],
        blocked_reasons=item.blocked_reasons or [],
        is_hidden=item.is_hidden,
        completed_action_id=str(item.completed_action_id) if item.completed_action_id else None,
        completed_at=item.completed_at,
        snoozed_until=item.snoozed_until,
        suppressed_until=item.suppressed_until,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/plots/{plot_id}/work-plan", response_model=list[WorkPlanItemResponse])
async def list_work_plan(
    plot_id: UUID,
    status: str | None = Query(default=None, pattern="^(planned|done|dismissed)$"),
    include_hidden: bool = False,
    include_snoozed: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plot = await _get_plot(plot_id, current_user.id, db)
    grid_data = plot.grid_data or {}
    changed = await dismiss_work_plan_items_not_in_grid(
        db,
        plot_id=plot.id,
        user_id=current_user.id,
        cells=grid_data.get("cells", []),
    )
    if changed:
        await db.commit()
    conditions = [
        WorkPlanItem.plot_id == plot_id,
        WorkPlanItem.user_id == current_user.id,
    ]
    if status:
        conditions.append(WorkPlanItem.status == status)
    if not include_hidden:
        conditions.append(WorkPlanItem.is_hidden.is_(False))
    if not include_snoozed:
        now = datetime.now(timezone.utc)
        conditions.append(
            or_(
                WorkPlanItem.snoozed_until.is_(None),
                WorkPlanItem.snoozed_until <= now,
            )
        )

    result = await db.execute(
        select(WorkPlanItem)
        .where(*conditions)
        .order_by(WorkPlanItem.status.asc(), WorkPlanItem.due_date.asc().nulls_last(), WorkPlanItem.created_at.desc())
    )
    return [_to_response(item) for item in result.scalars().all()]


@router.patch("/plots/{plot_id}/work-plan/{item_id}", response_model=WorkPlanItemResponse)
async def update_work_plan_item(
    plot_id: UUID,
    item_id: UUID,
    data: WorkPlanItemUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_plot(plot_id, current_user.id, db)
    item = await db.scalar(
        select(WorkPlanItem).where(
            WorkPlanItem.id == item_id,
            WorkPlanItem.plot_id == plot_id,
            WorkPlanItem.user_id == current_user.id,
        )
    )
    if not item:
        raise HTTPException(404, "Пункт плану не знайдено")

    if data.status is not None:
        if data.status not in {"planned", "done", "dismissed"}:
            raise HTTPException(400, "Некоректний статус пункту плану")
        if data.status == "done":
            complete_plan_item(item, completed_at=datetime.now(timezone.utc))
        elif data.status == "planned":
            item.status = "planned"
            item.completed_at = None
            item.completed_action_id = None
            item.suppressed_until = None
            item.snoozed_until = None
        else:
            item.status = data.status
    if "snoozed_until" in data.model_fields_set:
        item.snoozed_until = data.snoozed_until
    item.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(item)
    return _to_response(item)


@router.post("/plots/{plot_id}/work-plan/{item_id}/complete-action", response_model=WorkPlanItemResponse)
async def complete_work_plan_item_as_action(
    plot_id: UUID,
    item_id: UUID,
    data: WorkPlanCompleteAction | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record a work-plan item as factual work.

    This is intentionally separate from PATCH status=done. A plain status
    change only clears the queue item; this endpoint writes the agronomic
    journal entry that the engine can use as history.
    """
    await _get_plot(plot_id, current_user.id, db)
    item = await db.scalar(
        select(WorkPlanItem).where(
            WorkPlanItem.id == item_id,
            WorkPlanItem.plot_id == plot_id,
            WorkPlanItem.user_id == current_user.id,
        )
    )
    if not item:
        raise HTTPException(404, "Пункт плану не знайдено")

    payload = data or WorkPlanCompleteAction()
    action = GardenAction(
        plot_id=plot_id,
        user_id=current_user.id,
        action_type=action_type_for_task(item.task_type),
        plant_type=item.plant_type,
        variety=item.variety,
        cell_col=item.cell_col,
        cell_row=item.cell_row,
        amount=payload.amount if payload.amount is not None else item.amount,
        notes=payload.notes if payload.notes is not None else item.description,
        task_title=item.title,
        scope=payload.scope or ("single" if item.cell_col is not None and item.cell_row is not None else "all"),
    )
    db.add(action)
    await db.flush()

    now = action.created_at or datetime.now(timezone.utc)
    complete_plan_item(item, completed_at=now, completed_action_id=action.id)
    await ensure_treatment_for_action(db, action=action, work_plan_item=item)

    await db.commit()
    await db.refresh(item)
    return _to_response(item)
