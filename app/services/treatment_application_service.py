from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.garden_action import GardenAction
from app.models.treatment_application import TreatmentApplication
from app.models.work_plan_item import WorkPlanItem
from app.schemas.garden import TreatmentApplicationCreate
from app.services.fertilizer_profile_service import FERTILIZER_PROFILES
from app.services.protection_profile_service import PROTECTION_PROFILES
from app.services.work_plan_service import action_type_for_task


TREATMENT_ACTION_TYPES = {"fertilizing", "disease", "pest"}


def _decimal_or_none(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _text_blob(item: WorkPlanItem) -> str:
    parts = [
        item.title or "",
        item.description or "",
        item.recommendation_type or "",
        " ".join(item.reasons or []),
        " ".join(item.constraints or []),
    ]
    for values in (item.reason_groups or {}).values():
        parts.extend(str(value) for value in values)
    return " ".join(parts).lower()


def _infer_fertilizer_profile(item: WorkPlanItem):
    blob = _text_blob(item)
    for profile in FERTILIZER_PROFILES.values():
        if profile.label.lower() in blob:
            return profile
    for profile in FERTILIZER_PROFILES.values():
        if profile.fertilizer_type.lower() == (item.recommendation_type or "").lower():
            return profile
    return None


def _infer_protection_profile(item: WorkPlanItem):
    blob = _text_blob(item)
    for profile in PROTECTION_PROFILES.values():
        if profile.frac_group and f"frac {profile.frac_group.lower()}" in blob:
            return profile
    for profile in PROTECTION_PROFILES.values():
        if profile.protection_type.lower() == (item.recommendation_type or "").lower():
            return profile
    return None


def _target_problem(item: WorkPlanItem) -> str | None:
    title = item.title or ""
    if ":" in title:
        return title.split(":", 1)[1].split("—", 1)[0].strip() or None
    return None


def treatment_payload_from_work_plan(item: WorkPlanItem) -> dict | None:
    action_type = action_type_for_task(item.task_type)
    if action_type not in TREATMENT_ACTION_TYPES:
        return None

    base = {
        "plant_type": item.plant_type,
        "variety": item.variety,
        "cell_col": item.cell_col,
        "cell_row": item.cell_row,
        "scope": "single" if item.cell_col is not None and item.cell_row is not None else "all",
        "rate_amount": item.amount,
        "applied_amount": item.amount,
        "notes": item.description,
        "reasons": item.reasons or [],
        "metadata_json": {
            "source_task_type": item.task_type,
            "priority": item.priority,
            "confidence": item.confidence,
            "recommendation_type": item.recommendation_type,
            "constraints": item.constraints or [],
            "reason_groups": item.reason_groups or {},
        },
    }

    if action_type == "fertilizing":
        profile = _infer_fertilizer_profile(item)
        return {
            **base,
            "treatment_kind": "fertilizer",
            "product_profile_id": profile.id if profile else None,
            "product_name": profile.label if profile else item.recommendation_type,
            "product_type": profile.fertilizer_type if profile else item.recommendation_type,
            "application_method": profile.application_method if profile else None,
            "n_pct": profile.n_pct if profile else None,
            "p_pct": profile.p_pct if profile else None,
            "k_pct": profile.k_pct if profile else None,
            "mg_pct": profile.mg_pct if profile else None,
            "ca_pct": profile.ca_pct if profile else None,
        }

    profile = _infer_protection_profile(item)
    return {
        **base,
        "treatment_kind": "protection",
        "product_profile_id": profile.id if profile else None,
        "product_name": profile.label if profile else item.recommendation_type,
        "product_type": profile.protection_type if profile else item.recommendation_type,
        "application_method": profile.mode_of_action if profile else None,
        "target_problem": _target_problem(item),
        "frac_group": profile.frac_group if profile else None,
        "reentry_days": profile.reentry_days if profile else None,
        "pre_harvest_interval_days": profile.pre_harvest_interval_days if profile else None,
        "rainfast_hours": profile.rainfast_hours if profile else None,
    }


async def ensure_treatment_for_action(
    db: AsyncSession,
    *,
    action: GardenAction,
    work_plan_item: WorkPlanItem | None = None,
) -> TreatmentApplication | None:
    if action.action_type not in TREATMENT_ACTION_TYPES:
        return None

    existing = await db.scalar(
        select(TreatmentApplication).where(TreatmentApplication.garden_action_id == action.id)
    )
    if existing:
        return existing

    payload = treatment_payload_from_work_plan(work_plan_item) if work_plan_item else None
    if payload is None:
        payload = {
            "treatment_kind": "fertilizer" if action.action_type == "fertilizing" else "protection",
            "plant_type": action.plant_type,
            "variety": action.variety,
            "cell_col": action.cell_col,
            "cell_row": action.cell_row,
            "scope": action.scope,
            "rate_amount": action.amount,
            "applied_amount": action.amount,
            "notes": action.notes,
            "reasons": [],
            "metadata_json": {"source_action_type": action.action_type},
        }

    treatment = TreatmentApplication(
        plot_id=action.plot_id,
        user_id=action.user_id,
        garden_action_id=action.id,
        work_plan_item_id=work_plan_item.id if work_plan_item else None,
        applied_at=action.created_at or datetime.now(timezone.utc),
        **payload,
    )
    db.add(treatment)
    await db.flush()
    return treatment


async def create_manual_treatment(
    db: AsyncSession,
    *,
    plot_id,
    user_id,
    data: TreatmentApplicationCreate,
) -> TreatmentApplication:
    action_type = "fertilizing" if data.treatment_kind == "fertilizer" else "disease"
    action = GardenAction(
        plot_id=plot_id,
        user_id=user_id,
        action_type=action_type,
        plant_type=data.plant_type,
        variety=data.variety,
        cell_col=data.cell_col,
        cell_row=data.cell_row,
        amount=data.applied_amount or data.rate_amount,
        notes=data.notes,
        task_title=data.product_name,
        scope=data.scope,
    )
    db.add(action)
    await db.flush()

    treatment = TreatmentApplication(
        plot_id=plot_id,
        user_id=user_id,
        garden_action_id=action.id,
        treatment_kind=data.treatment_kind,
        source="manual",
        plant_type=data.plant_type,
        variety=data.variety,
        cell_col=data.cell_col,
        cell_row=data.cell_row,
        scope=data.scope,
        product_profile_id=data.product_profile_id,
        product_name=data.product_name,
        product_type=data.product_type,
        application_method=data.application_method,
        target_problem=data.target_problem,
        frac_group=data.frac_group,
        n_pct=_decimal_or_none(data.n_pct),
        p_pct=_decimal_or_none(data.p_pct),
        k_pct=_decimal_or_none(data.k_pct),
        mg_pct=_decimal_or_none(data.mg_pct),
        ca_pct=_decimal_or_none(data.ca_pct),
        reentry_days=data.reentry_days,
        pre_harvest_interval_days=data.pre_harvest_interval_days,
        rainfast_hours=data.rainfast_hours,
        rate_amount=data.rate_amount,
        area_sqm=_decimal_or_none(data.area_sqm),
        applied_amount=data.applied_amount,
        notes=data.notes,
        reasons=data.reasons,
        metadata_json=data.metadata_json,
    )
    db.add(treatment)
    await db.flush()
    return treatment
