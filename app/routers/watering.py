"""
Watering Router — розумний полив (тільки Premium).
"""
from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import require_premium
from app.models.user import User
from app.models.watering import WateringRecommendation
from app.models.plant import Plant
from app.models.crop import CropCatalog
from app.schemas.watering import WateringRecommendationResponse, WateringActionRequest

router = APIRouter(prefix="/watering", tags=["watering"])
PremiumUser = Depends(require_premium("smart_watering"))


@router.get("/today", response_model=list[WateringRecommendationResponse])
async def get_today_watering(
    current_user: User = PremiumUser,
    db: AsyncSession = Depends(get_db),
):
    """Список рослин для поливу сьогодні."""
    result = await db.execute(
        select(WateringRecommendation, Plant.name.label("plant_name"), CropCatalog.name_uk.label("crop_name"))
        .join(Plant, WateringRecommendation.plant_id == Plant.id)
        .join(CropCatalog, Plant.crop_id == CropCatalog.id)
        .where(
            Plant.user_id == current_user.id,
            WateringRecommendation.recommended_date == date.today(),
            WateringRecommendation.status == "pending",
        )
        .order_by(WateringRecommendation.recommended_amount_ml.desc())
    )
    rows = result.all()

    return [
        {
            **rec.__dict__,
            "plant_name": plant_name,
            "crop_name": crop_name,
        }
        for rec, plant_name, crop_name in rows
    ]


@router.post("/{rec_id}/action", response_model=dict)
async def watering_action(
    rec_id: UUID,
    data: WateringActionRequest,
    current_user: User = PremiumUser,
    db: AsyncSession = Depends(get_db),
):
    """Відмітити рекомендацію як виконано / пропустити."""
    from app.models.care_journal import CareJournal
    from datetime import datetime, timezone

    rec = await _get_rec_or_404(rec_id, current_user.id, db)

    status_map = {"done": "done", "skip": "skipped", "rain_cancelled": "rain_cancelled"}
    rec.status = status_map.get(data.action, "skipped")

    # Якщо виконано — додаємо запис у журнал автоматично
    if data.action == "done":
        from uuid import uuid4
        journal_entry = CareJournal(
            id=uuid4(),
            plant_id=rec.plant_id,
            user_id=current_user.id,
            care_type="watering",
            performed_at=datetime.now(timezone.utc),
            details={"amount_ml": data.actual_amount_ml or rec.recommended_amount_ml, "source": "auto_recommendation"},
            synced_at=datetime.now(timezone.utc),
        )
        db.add(journal_entry)

        # Оновлюємо last_watered_at
        plant = await db.get(Plant, rec.plant_id)
        if plant:
            plant.last_watered_at = datetime.now(timezone.utc)

    await db.commit()
    return {"status": rec.status, "rec_id": str(rec_id)}


@router.get("/settings/{plant_id}")
async def get_watering_settings(
    plant_id: UUID,
    current_user: User = PremiumUser,
    db: AsyncSession = Depends(get_db),
):
    """Налаштування алгоритму поливу для конкретної рослини."""
    plant = await db.scalar(
        select(Plant).where(Plant.id == plant_id, Plant.user_id == current_user.id)
    )
    if not plant:
        raise HTTPException(status_code=404, detail="Рослину не знайдено")

    crop = await db.get(CropCatalog, plant.crop_id)
    return {
        "plant_id": str(plant_id),
        "crop_water_need_ml": crop.water_need_ml_per_day if crop else None,
        "crop_drought_tolerance": crop.drought_tolerance if crop else None,
        "auto_adjust_for_rain": True,
        "rain_threshold_mm": 5.0,
        "rain_probability_threshold": 70.0,
    }


async def _get_rec_or_404(rec_id, user_id, db) -> WateringRecommendation:
    rec = await db.scalar(
        select(WateringRecommendation)
        .join(Plant, WateringRecommendation.plant_id == Plant.id)
        .where(WateringRecommendation.id == rec_id, Plant.user_id == user_id)
    )
    if not rec:
        raise HTTPException(status_code=404, detail="Рекомендацію не знайдено")
    return rec
