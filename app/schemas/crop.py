import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.services.lifecycle_types import LifecycleType


class CropCreate(BaseModel):
    name_uk: str = Field(max_length=100)
    name_en: str | None = None
    scientific_name: str | None = None
    category: str | None = None
    lifecycle_type: LifecycleType = LifecycleType.ANNUAL
    t_base: float = Field(10.0, ge=0, le=30)
    t_optimal_min: float | None = None
    t_optimal_max: float | None = None
    water_need_ml_per_day: int | None = Field(None, ge=0)
    drought_tolerance: int | None = Field(None, ge=1, le=5)
    sun_requirement: str | None = None
    min_daily_sun_hours: float | None = None
    growth_stages: list[dict[str, Any]] = []
    description: str | None = None


class CropListOut(BaseModel):
    id: uuid.UUID
    name_uk: str
    name_en: str | None
    category: str | None
    lifecycle_type: str = "annual"
    icon_url: str | None
    t_base: float
    sun_requirement: str | None

    model_config = {"from_attributes": True}


class CropOut(CropListOut):
    scientific_name: str | None
    t_optimal_min: float | None
    t_optimal_max: float | None
    water_need_ml_per_day: int | None
    drought_tolerance: int | None
    min_daily_sun_hours: float | None
    growth_stages: list[dict[str, Any]]
    common_diseases: list[dict[str, Any]]
    description: str | None
    is_system: bool
    created_at: datetime
