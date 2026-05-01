from pydantic import BaseModel, UUID4
from datetime import date, datetime
from typing import Literal


class WateringRecommendationResponse(BaseModel):
    id: UUID4
    plant_id: UUID4
    plant_name: str | None
    crop_name: str | None
    recommended_date: date
    recommended_amount_ml: int | None
    reason_factors: dict
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class WateringActionRequest(BaseModel):
    action: Literal["done", "skip", "rain_cancelled"]
    actual_amount_ml: int | None = None   # якщо done


class WateringSettingsResponse(BaseModel):
    plant_id: UUID4
    auto_adjust_for_rain: bool = True
    rain_threshold_mm: float = 5.0
    rain_probability_threshold: float = 70.0
    custom_water_need_ml: int | None = None
