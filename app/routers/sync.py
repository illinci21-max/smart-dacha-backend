"""
Sync Router — офлайн-синхронізація.

Протокол:
1. Клієнт накопичує зміни офлайн (SQLite на пристрої), всі id — UUID v4 з клієнта
2. При появі інтернету — POST /sync/batch зі списком змін
3. Сервер відповідає: accepted, conflicts, server_changes
4. Conflict resolution: last-write-wins по полю updated_at
"""
from uuid import UUID
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.care_journal import CareJournal
from app.models.plant import Plant
from app.models.plot import Plot
from app.schemas.sync import SyncBatchRequest, SyncBatchResponse, SyncItem, ConflictItem

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/batch", response_model=SyncBatchResponse)
async def sync_batch(
    request: SyncBatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Батчева синхронізація офлайн-змін.
    Обробляє до 500 елементів за один запит.
    """
    if len(request.items) > 500:
        raise HTTPException(status_code=413, detail="Максимум 500 елементів за один запит")

    accepted: list[UUID] = []
    conflicts: list[ConflictItem] = []

    for item in request.items:
        try:
            result = await _process_sync_item(item, current_user.id, db)
            if result["status"] == "accepted":
                accepted.append(item.id)
            elif result["status"] == "conflict":
                conflicts.append(ConflictItem(
                    id=item.id,
                    entity_type=item.entity_type,
                    server_version=result["server_version"],
                    client_updated_at=item.updated_at,
                    server_updated_at=result["server_updated_at"],
                    resolution="server_wins",
                ))
        except Exception as e:
            # Не зупиняємо весь батч через один елемент
            conflicts.append(ConflictItem(
                id=item.id,
                entity_type=item.entity_type,
                server_version={},
                client_updated_at=item.updated_at,
                server_updated_at=datetime.now(timezone.utc),
                resolution="manual_required",
            ))

    # Повертаємо зміни на сервері після last_sync
    server_changes = []
    if request.last_sync_timestamp:
        server_changes = await _get_server_changes(current_user.id, request.last_sync_timestamp, db)

    await db.commit()

    return SyncBatchResponse(
        accepted=accepted,
        conflicts=conflicts,
        server_changes=server_changes,
        sync_timestamp=datetime.now(timezone.utc),
        total_server_changes=len(server_changes),
    )


async def _process_sync_item(item: SyncItem, user_id: UUID, db: AsyncSession) -> dict:
    """
    Обробляє один елемент синхронізації.
    Повертає {"status": "accepted"} або {"status": "conflict", "server_version": ...}
    """
    handlers = {
        "care_journal": _sync_journal_entry,
        "plant": _sync_plant,
        "plot": _sync_plot,
    }
    handler = handlers.get(item.entity_type)
    if not handler:
        raise ValueError(f"Unknown entity_type: {item.entity_type}")

    return await handler(item, user_id, db)


async def _sync_journal_entry(item: SyncItem, user_id: UUID, db: AsyncSession) -> dict:
    existing = await db.get(CareJournal, item.id)

    if item.operation == "delete":
        if existing and existing.user_id == user_id:
            existing.is_deleted = True
            existing.updated_at = item.updated_at
        return {"status": "accepted"}

    # Upsert
    if existing is None:
        # Новий запис — вставляємо
        payload = _sanitize_payload(item.payload, user_id)
        entry = CareJournal(
            id=item.id,
            user_id=user_id,
            device_created_at=item.device_created_at,
            updated_at=item.updated_at,
            synced_at=datetime.now(timezone.utc),
            **payload,
        )
        db.add(entry)
        return {"status": "accepted"}

    # Запис існує — перевіряємо конфлікт
    if existing.user_id != user_id:
        raise PermissionError("Access denied")

    if item.updated_at > existing.updated_at:
        # Клієнт новіший — оновлюємо (last-write-wins)
        for key, value in _sanitize_payload(item.payload, user_id).items():
            setattr(existing, key, value)
        existing.updated_at = item.updated_at
        existing.synced_at = datetime.now(timezone.utc)
        return {"status": "accepted"}
    else:
        # Сервер новіший — повертаємо конфлікт
        return {
            "status": "conflict",
            "server_version": {
                "id": str(existing.id),
                "care_type": existing.care_type,
                "performed_at": existing.performed_at.isoformat(),
                "updated_at": existing.updated_at.isoformat(),
            },
            "server_updated_at": existing.updated_at,
        }


async def _sync_plant(item: SyncItem, user_id: UUID, db: AsyncSession) -> dict:
    existing = await db.get(Plant, item.id)

    if item.operation == "delete":
        if existing and existing.user_id == user_id:
            existing.is_deleted = True
        return {"status": "accepted"}

    if existing is None:
        payload = item.payload.copy()
        payload.pop("user_id", None)
        plant = Plant(id=item.id, user_id=user_id, updated_at=item.updated_at, **payload)
        db.add(plant)
        return {"status": "accepted"}

    if existing.user_id != user_id:
        raise PermissionError("Access denied")

    if item.updated_at > existing.updated_at:
        for key, value in item.payload.items():
            if key not in ("id", "user_id") and hasattr(existing, key):
                setattr(existing, key, value)
        existing.updated_at = item.updated_at
        return {"status": "accepted"}

    return {
        "status": "conflict",
        "server_version": {"id": str(existing.id), "updated_at": existing.updated_at.isoformat()},
        "server_updated_at": existing.updated_at,
    }


async def _sync_plot(item: SyncItem, user_id: UUID, db: AsyncSession) -> dict:
    existing = await db.get(Plot, item.id)

    if item.operation == "delete":
        if existing and existing.user_id == user_id:
            existing.is_deleted = True
        return {"status": "accepted"}

    if existing is None:
        payload = item.payload.copy()
        payload.pop("user_id", None)
        plot = Plot(id=item.id, user_id=user_id, updated_at=item.updated_at, **payload)
        db.add(plot)
        return {"status": "accepted"}

    if existing.user_id != user_id:
        raise PermissionError("Access denied")

    if item.updated_at > existing.updated_at:
        for key, value in item.payload.items():
            if key not in ("id", "user_id") and hasattr(existing, key):
                setattr(existing, key, value)
        existing.updated_at = item.updated_at
        return {"status": "accepted"}

    return {
        "status": "conflict",
        "server_version": {"id": str(existing.id), "updated_at": existing.updated_at.isoformat()},
        "server_updated_at": existing.updated_at,
    }


async def _get_server_changes(user_id: UUID, since: datetime, db: AsyncSession) -> list[dict]:
    """Повертає всі зміни на сервері після вказаного timestamp."""
    result = await db.execute(
        select(CareJournal)
        .where(CareJournal.user_id == user_id, CareJournal.updated_at > since)
        .order_by(CareJournal.updated_at.asc())
        .limit(500)
    )
    entries = result.scalars().all()

    return [
        {
            "entity_type": "care_journal",
            "id": str(e.id),
            "operation": "delete" if e.is_deleted else "upsert",
            "updated_at": e.updated_at.isoformat(),
            "payload": {
                "plant_id": str(e.plant_id),
                "care_type": e.care_type,
                "performed_at": e.performed_at.isoformat(),
                "details": e.details,
                "notes": e.notes,
                "is_deleted": e.is_deleted,
            },
        }
        for e in entries
    ]


def _sanitize_payload(payload: dict, user_id: UUID) -> dict:
    """Видаляє небезпечні поля з payload клієнта."""
    blocked = {"user_id", "synced_at", "id"}
    return {k: v for k, v in payload.items() if k not in blocked}


@router.get("/status")
async def get_sync_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Статус синхронізації: кількість несинхронізованих записів."""
    from sqlalchemy import func
    unsynced = await db.scalar(
        select(func.count()).where(
            CareJournal.user_id == current_user.id,
            CareJournal.synced_at == None,
            CareJournal.is_deleted == False,
        )
    )
    return {
        "unsynced_count": unsynced,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }
