from pydantic import BaseModel, UUID4, field_validator
from datetime import datetime, date
from decimal import Decimal
import uuid


class PlantCreate(BaseModel):
    # FIX: id має default=uuid.uuid4 — клієнт може не передавати
    id: UUID4 = None
    crop_id: UUID4
    name: str | None = None
    quantity: int = 1
    planted_date: date | None = None

    @field_validator("id", mode="before")
    @classmethod
    def set_id(cls, v):
        return v or uuid.uuid4()


class PlantUpdate(BaseModel):
    name: str | None = None
    quantity: int | None = None
    planted_date: date | None = None


class PlantResponse(BaseModel):
    id: UUID4
    plot_id: UUID4
    user_id: UUID4
    crop_id: UUID4
    name: str | None
    quantity: int
    planted_date: date | None
    sat_accumulated: Decimal
    sat_last_updated_at: date | None
    current_growth_stage: str | None
    insolation_accumulated_wh: Decimal
    last_watered_at: datetime | None
    is_deleted: bool
    updated_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
