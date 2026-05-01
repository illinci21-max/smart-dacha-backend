"""Garden actions backed by a proper table instead of plot.grid_data JSONB."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.garden_action import GardenAction
from app.models.plot import Plot
from app.models.treatment_application import TreatmentApplication
from app.models.user import User
from app.schemas.garden import (
    GardenActionCreate,
    GardenActionResponse,
    TreatmentApplicationCreate,
    TreatmentApplicationResponse,
)
from app.services.treatment_application_service import (
    create_manual_treatment,
    ensure_treatment_for_action,
)
from app.services.work_plan_service import mark_matching_work_plan_done

router = APIRouter(prefix="/garden", tags=["garden-actions"])


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


def _to_response(action: GardenAction) -> GardenActionResponse:
    return GardenActionResponse(
        id=str(action.id),
        action_type=action.action_type,
        plant_type=action.plant_type,
        variety=action.variety,
        cell_col=action.cell_col,
        cell_row=action.cell_row,
        amount=action.amount,
        notes=action.notes,
        task_title=action.task_title,
        scope=action.scope,
        created_at=action.created_at,
    )


def _treatment_to_response(treatment: TreatmentApplication) -> TreatmentApplicationResponse:
    return TreatmentApplicationResponse(
        id=str(treatment.id),
        plot_id=treatment.plot_id,
        garden_action_id=str(treatment.garden_action_id) if treatment.garden_action_id else None,
        work_plan_item_id=str(treatment.work_plan_item_id) if treatment.work_plan_item_id else None,
        source=treatment.source,
        treatment_kind=treatment.treatment_kind,
        plant_type=treatment.plant_type,
        variety=treatment.variety,
        cell_col=treatment.cell_col,
        cell_row=treatment.cell_row,
        scope=treatment.scope,
        product_profile_id=treatment.product_profile_id,
        product_name=treatment.product_name,
        product_type=treatment.product_type,
        application_method=treatment.application_method,
        target_problem=treatment.target_problem,
        frac_group=treatment.frac_group,
        n_pct=float(treatment.n_pct) if treatment.n_pct is not None else None,
        p_pct=float(treatment.p_pct) if treatment.p_pct is not None else None,
        k_pct=float(treatment.k_pct) if treatment.k_pct is not None else None,
        mg_pct=float(treatment.mg_pct) if treatment.mg_pct is not None else None,
        ca_pct=float(treatment.ca_pct) if treatment.ca_pct is not None else None,
        reentry_days=treatment.reentry_days,
        pre_harvest_interval_days=treatment.pre_harvest_interval_days,
        rainfast_hours=treatment.rainfast_hours,
        rate_amount=treatment.rate_amount,
        area_sqm=float(treatment.area_sqm) if treatment.area_sqm is not None else None,
        applied_amount=treatment.applied_amount,
        notes=treatment.notes,
        reasons=treatment.reasons or [],
        metadata_json=treatment.metadata_json or {},
        applied_at=treatment.applied_at,
        created_at=treatment.created_at,
    )


@router.post("/plots/{plot_id}/actions", response_model=GardenActionResponse, status_code=201)
async def log_garden_action(
    plot_id: UUID,
    data: GardenActionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_plot(plot_id, current_user.id, db)
    action = GardenAction(
        plot_id=plot_id,
        user_id=current_user.id,
        action_type=data.action_type,
        plant_type=data.plant_type,
        variety=data.variety,
        cell_col=data.cell_col,
        cell_row=data.cell_row,
        amount=data.amount,
        notes=data.notes,
        task_title=data.task_title,
        scope=data.scope,
    )
    db.add(action)
    await db.flush()
    matched_items = await mark_matching_work_plan_done(
        db,
        plot_id=plot_id,
        user_id=current_user.id,
        action=action,
    )
    await ensure_treatment_for_action(
        db,
        action=action,
        work_plan_item=matched_items[0] if matched_items else None,
    )
    await db.commit()
    await db.refresh(action)
    return _to_response(action)


@router.post("/plots/{plot_id}/treatments", response_model=TreatmentApplicationResponse, status_code=201)
async def create_treatment_application(
    plot_id: UUID,
    data: TreatmentApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_plot(plot_id, current_user.id, db)
    if data.treatment_kind not in {"fertilizer", "protection"}:
        raise HTTPException(400, "Unsupported treatment_kind")
    treatment = await create_manual_treatment(
        db,
        plot_id=plot_id,
        user_id=current_user.id,
        data=data,
    )
    await db.commit()
    await db.refresh(treatment)
    return _treatment_to_response(treatment)


@router.get("/plots/{plot_id}/treatments", response_model=list[TreatmentApplicationResponse])
async def list_treatment_applications(
    plot_id: UUID,
    days: int = 180,
    treatment_kind: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_plot(plot_id, current_user.id, db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 730)))
    conditions = [
        TreatmentApplication.plot_id == plot_id,
        TreatmentApplication.user_id == current_user.id,
        TreatmentApplication.applied_at >= cutoff,
    ]
    if treatment_kind:
        conditions.append(TreatmentApplication.treatment_kind == treatment_kind)
    result = await db.execute(
        select(TreatmentApplication)
        .where(*conditions)
        .order_by(TreatmentApplication.applied_at.desc())
    )
    return [_treatment_to_response(item) for item in result.scalars().all()]


@router.get("/plots/{plot_id}/actions", response_model=list[GardenActionResponse])
async def list_garden_actions(
    plot_id: UUID,
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_plot(plot_id, current_user.id, db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)))
    result = await db.execute(
        select(GardenAction)
        .where(
            GardenAction.plot_id == plot_id,
            GardenAction.user_id == current_user.id,
            GardenAction.created_at >= cutoff,
        )
        .order_by(GardenAction.created_at.desc())
    )
    return [_to_response(action) for action in result.scalars().all()]


@router.delete("/plots/{plot_id}/actions/{action_id}", status_code=204)
async def delete_garden_action(
    plot_id: UUID,
    action_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_plot(plot_id, current_user.id, db)
    action = await db.scalar(
        select(GardenAction).where(
            GardenAction.id == action_id,
            GardenAction.plot_id == plot_id,
            GardenAction.user_id == current_user.id,
        )
    )
    if not action:
        raise HTTPException(404, "Дію не знайдено")
    await db.delete(action)
    await db.commit()
    return None
