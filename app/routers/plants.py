"""
Plants Router — управління рослинами на ділянках.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user, require_premium
from app.models.user import User
from app.models.plant import Plant
from app.models.plot import Plot
from app.models.crop import CropCatalog
from app.schemas.plant import PlantCreate, PlantUpdate, PlantResponse

router = APIRouter(tags=["plants"])


@router.get("/plots/{plot_id}/plants", response_model=list[PlantResponse])
async def list_plants(
    plot_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_plot_access(plot_id, current_user.id, db)
    result = await db.execute(
        select(Plant).where(Plant.plot_id == plot_id, Plant.is_deleted == False)
    )
    plants = result.scalars().all()
    return plants


@router.post("/plots/{plot_id}/plants", response_model=PlantResponse, status_code=201)
async def create_plant(
    plot_id: UUID,
    data: PlantCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Перевірка ліміту рослин
    from sqlalchemy import func
    count = await db.scalar(
        select(func.count()).where(Plant.user_id == current_user.id, Plant.is_deleted == False)
    )
    if count >= current_user.plants_limit:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "plants_limit_reached",
                "current": count,
                "limit": current_user.plants_limit,
                "message": "Досягнуто ліміт рослин. Оновіть до Premium.",
            },
        )

    await _check_plot_access(plot_id, current_user.id, db)

    # Перевіряємо існування культури
    crop = await db.get(CropCatalog, data.crop_id)
    if not crop:
        raise HTTPException(status_code=404, detail="Культуру не знайдено в довіднику")

    plant_data = data.model_dump(exclude={"id"})
    plant = Plant(
        id=data.id,   # UUID з клієнта для офлайн-синхронізації
        plot_id=plot_id,
        user_id=current_user.id,
        **{k: v for k, v in plant_data.items() if k != "plot_id"},
    )
    db.add(plant)
    await db.commit()
    await db.refresh(plant)
    return plant


@router.get("/plants/{plant_id}", response_model=PlantResponse)
async def get_plant(
    plant_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plant = await _get_plant_or_404(plant_id, current_user.id, db)
    return plant


@router.put("/plants/{plant_id}", response_model=PlantResponse)
async def update_plant(
    plant_id: UUID,
    data: PlantUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plant = await _get_plant_or_404(plant_id, current_user.id, db)
    for key, value in data.model_dump(exclude_none=True).items():
        setattr(plant, key, value)
    await db.commit()
    await db.refresh(plant)
    return plant


@router.delete("/plants/{plant_id}", status_code=204)
async def delete_plant(
    plant_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plant = await _get_plant_or_404(plant_id, current_user.id, db)
    plant.is_deleted = True
    await db.commit()


@router.get("/plants/{plant_id}/sat-history")
async def get_sat_history(
    plant_id: UUID,
    current_user: User = Depends(require_premium("sat_history")),
    db: AsyncSession = Depends(get_db),
):
    """Графік САТ за поточний сезон (тільки Premium)."""
    plant = await _get_plant_or_404(plant_id, current_user.id, db)
    crop = await db.get(CropCatalog, plant.crop_id)

    return {
        "plant_id": str(plant_id),
        "sat_accumulated": float(plant.sat_accumulated),
        "sat_reset_date": str(plant.sat_reset_date) if plant.sat_reset_date else None,
        "current_growth_stage": plant.current_growth_stage,
        "insolation_accumulated_wh": float(plant.insolation_accumulated_wh),
        "growth_stages": crop.growth_stages if crop else [],
        "t_base": float(crop.t_base) if crop else 10.0,
    }


@router.get("/plants/{plant_id}/watering-schedule")
async def get_watering_schedule(
    plant_id: UUID,
    current_user: User = Depends(require_premium("smart_watering")),
    db: AsyncSession = Depends(get_db),
):
    """Розклад поливу на 7 днів (тільки Premium)."""
    from app.models.watering import WateringRecommendation
    from datetime import date

    plant = await _get_plant_or_404(plant_id, current_user.id, db)

    result = await db.execute(
        select(WateringRecommendation)
        .where(
            WateringRecommendation.plant_id == plant_id,
            WateringRecommendation.recommended_date >= date.today(),
            WateringRecommendation.status == "pending",
        )
        .order_by(WateringRecommendation.recommended_date)
        .limit(7)
    )
    recs = result.scalars().all()

    return [
        {
            "date": str(r.recommended_date),
            "amount_ml": r.recommended_amount_ml,
            "urgency": r.reason_factors.get("urgency", "medium"),
            "status": r.status,
            "rec_id": str(r.id),
        }
        for r in recs
    ]


async def _check_plot_access(plot_id, user_id, db):
    plot = await db.scalar(
        select(Plot).where(Plot.id == plot_id, Plot.user_id == user_id, Plot.is_deleted == False)
    )
    if not plot:
        raise HTTPException(status_code=404, detail="Ділянку не знайдено або доступ заборонено")
    return plot


async def _get_plant_or_404(plant_id, user_id, db) -> Plant:
    plant = await db.scalar(
        select(Plant).where(
            Plant.id == plant_id,
            Plant.user_id == user_id,
            Plant.is_deleted == False,
        )
    )
    if not plant:
        raise HTTPException(status_code=404, detail="Рослину не знайдено")
    return plant
