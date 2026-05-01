"""
Catalog Router — довідник культур.
"""
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.dialects.postgresql import TSVECTOR

from app.database import get_db
from app.dependencies import get_current_user, require_premium
from app.models.user import User
from app.models.crop import CropCatalog
from app.schemas.catalog import CropCreate, CropResponse

router = APIRouter(prefix="/catalog", tags=["catalog"])

CROP_CATEGORIES = ["vegetable", "fruit", "berry", "herb", "flower", "tree", "shrub", "grain"]


@router.get("/crops", response_model=list[CropResponse])
async def search_crops(
    q: str | None = Query(default=None, description="Пошук по назві"),
    category: str | None = Query(default=None, description="Категорія культури"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Пошук по довіднику культур (публічний, без авторизації)."""
    query = select(CropCatalog).where(CropCatalog.is_system == True)

    if q:
        # Full-text пошук по назві
        search_term = f"%{q.lower()}%"
        query = query.where(
            or_(
                CropCatalog.name_uk.ilike(search_term),
                CropCatalog.name_en.ilike(search_term),
            )
        )
    if category and category in CROP_CATEGORIES:
        query = query.where(CropCatalog.category == category)

    query = query.offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/crops/{crop_id}", response_model=CropResponse)
async def get_crop(crop_id: UUID, db: AsyncSession = Depends(get_db)):
    """Деталі культури з довідника."""
    crop = await db.get(CropCatalog, crop_id)
    if not crop:
        raise HTTPException(status_code=404, detail="Культуру не знайдено")
    return crop


@router.get("/crops/{crop_id}/diseases")
async def get_crop_diseases(crop_id: UUID, db: AsyncSession = Depends(get_db)):
    """Список хвороб та шкідників для культури."""
    crop = await db.get(CropCatalog, crop_id)
    if not crop:
        raise HTTPException(status_code=404, detail="Культуру не знайдено")
    return {"crop_id": str(crop_id), "diseases": crop.common_diseases or []}


@router.post("/crops", response_model=CropResponse, status_code=201)
async def create_custom_crop(
    data: CropCreate,
    current_user: User = Depends(require_premium("custom_crops")),
    db: AsyncSession = Depends(get_db),
):
    """Додати власну культуру (тільки Premium)."""
    crop = CropCatalog(
        **data.model_dump(exclude={"growth_stages", "common_diseases"}),
        growth_stages=[s.model_dump() for s in data.growth_stages],
        common_diseases=[d.model_dump() for d in data.common_diseases],
        is_system=False,
        created_by=current_user.id,
    )
    db.add(crop)
    await db.commit()
    await db.refresh(crop)
    return crop


@router.get("/categories")
async def get_categories():
    """Список категорій культур."""
    return {"categories": CROP_CATEGORIES}
