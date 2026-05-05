from pydantic import BaseModel, UUID4
from decimal import Decimal
from datetime import datetime

from app.services.lifecycle_types import LifecycleType


class GrowthStage(BaseModel):
    name: str
    sat_from: float
    sat_to: float
    description: str | None = None


class Disease(BaseModel):
    id: str
    name: str
    symptoms: str | None = None
    treatment: str | None = None


class CropBase(BaseModel):
    name_uk: str
    name_en: str | None = None
    category: str | None = None
    emoji: str | None = None
    lifecycle_type: LifecycleType = LifecycleType.ANNUAL
    t_base: Decimal = Decimal("10.0")
    water_need_ml_per_day: int | None = None
    drought_tolerance: int | None = None
    sun_requirement: str | None = None
    growth_stages: list[GrowthStage] = []
    common_diseases: list[Disease] = []
    description: str | None = None


class CropCreate(CropBase):
    pass


class CropResponse(CropBase):
    id: UUID4
    scientific_name: str | None
    lifecycle_type: str = "annual"
    t_optimal_min: Decimal | None
    t_optimal_max: Decimal | None
    min_daily_sun_hours: Decimal | None
    is_system: bool
    created_at: datetime

    model_config = {"from_attributes": True}
