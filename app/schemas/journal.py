from pydantic import BaseModel, UUID4
from datetime import datetime
from typing import Any


class PhotoItem(BaseModel):
    url: str
    thumbnail_url: str | None = None
    taken_at: datetime | None = None


class JournalEntryCreate(BaseModel):
    id: UUID4                          # UUID генерується на клієнті!
    plant_id: UUID4
    care_type: str
    performed_at: datetime
    details: dict[str, Any] = {}
    notes: str | None = None
    photos: list[PhotoItem] = []
    device_created_at: datetime | None = None


class JournalEntryUpdate(BaseModel):
    care_type: str | None = None
    performed_at: datetime | None = None
    details: dict[str, Any] | None = None
    notes: str | None = None
    updated_at: datetime                # обов'язково для conflict resolution


class JournalEntryResponse(BaseModel):
    id: UUID4
    plant_id: UUID4
    user_id: UUID4
    care_type: str
    performed_at: datetime
    details: dict
    notes: str | None
    photos: list
    ai_diagnosis_id: UUID4 | None
    is_deleted: bool
    updated_at: datetime
    synced_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
