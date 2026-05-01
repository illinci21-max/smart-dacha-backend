from pydantic import BaseModel, UUID4
from datetime import datetime
from typing import Literal, Any


class SyncItem(BaseModel):
    id: UUID4
    entity_type: Literal["care_journal", "plant", "plot"]
    operation: Literal["upsert", "delete"]
    payload: dict[str, Any]
    updated_at: datetime
    device_created_at: datetime


class ConflictItem(BaseModel):
    id: UUID4
    entity_type: str
    server_version: dict
    client_updated_at: datetime
    server_updated_at: datetime
    resolution: Literal["server_wins", "client_wins", "manual_required"]


class SyncBatchRequest(BaseModel):
    items: list[SyncItem]
    last_sync_timestamp: datetime | None = None
    device_id: str | None = None


class SyncBatchResponse(BaseModel):
    accepted: list[UUID4]
    conflicts: list[ConflictItem]
    server_changes: list[dict]
    sync_timestamp: datetime          # час сервера — зберегти на клієнті
    total_server_changes: int
