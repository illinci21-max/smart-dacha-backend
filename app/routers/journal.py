"""
Journal Router — журнал догляду за рослинами.
Підтримує офлайн-синхронізацію через UUID з клієнта.
"""
from uuid import UUID, uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.plant import Plant
from app.models.care_journal import CareJournal
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate, JournalEntryResponse
from app.config import settings

router = APIRouter(tags=["journal"])

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.get("/plants/{plant_id}/journal", response_model=list[JournalEntryResponse])
async def list_journal(
    plant_id: UUID,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    care_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_plant_access(plant_id, current_user.id, db)

    # FIX: WHERE з care_type має бути в основному запиті, не додаватися після offset/limit
    query = (
        select(CareJournal)
        .where(
            CareJournal.plant_id == plant_id,
            CareJournal.is_deleted == False,
            *([] if not care_type else [CareJournal.care_type == care_type]),
        )
        .order_by(CareJournal.performed_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/plants/{plant_id}/journal", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(
    plant_id: UUID,
    data: JournalEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_plant_access(plant_id, current_user.id, db)

    # Ідемпотентність для офлайн-sync
    existing = await db.get(CareJournal, data.id)
    if existing:
        return existing

    entry = CareJournal(
        id=data.id,
        plant_id=plant_id,
        user_id=current_user.id,
        care_type=data.care_type,
        performed_at=data.performed_at,
        details=data.details,
        notes=data.notes,
        photos=[p.model_dump() for p in data.photos],
        device_created_at=data.device_created_at or datetime.now(timezone.utc),
        synced_at=datetime.now(timezone.utc),
    )
    db.add(entry)

    if data.care_type == "watering":
        plant = await db.get(Plant, plant_id)
        if plant:
            plant.last_watered_at = data.performed_at

    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/journal/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_entry_or_404(entry_id, current_user.id, db)


@router.put("/journal/{entry_id}", response_model=JournalEntryResponse)
async def update_journal_entry(
    entry_id: UUID,
    data: JournalEntryUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await _get_entry_or_404(entry_id, current_user.id, db)

    if data.updated_at <= entry.updated_at:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "conflict",
                "message": "Сервер має новішу версію запису",
                "server_updated_at": entry.updated_at.isoformat(),
                "client_updated_at": data.updated_at.isoformat(),
            },
        )

    update_data = data.model_dump(exclude_none=True, exclude={"updated_at"})
    for key, value in update_data.items():
        setattr(entry, key, value)
    entry.synced_at = datetime.now(timezone.utc)
    # FIX: не виставляємо updated_at вручну — нехай onupdate=func.now() зробить це
    # Але якщо клієнт передав updated_at — зберігаємо його для синхронізації
    entry.updated_at = data.updated_at

    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/journal/{entry_id}", status_code=204)
async def delete_journal_entry(
    entry_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entry = await _get_entry_or_404(entry_id, current_user.id, db)
    entry.is_deleted = True
    entry.updated_at = datetime.now(timezone.utc)
    await db.commit()


@router.post("/journal/{entry_id}/photo")
async def upload_photo(
    entry_id: UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Завантаження фото до запису журналу."""
    entry = await _get_entry_or_404(entry_id, current_user.id, db)

    # FIX: Валідація типу файлу
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Підтримуються тільки JPEG, PNG, WebP")

    max_photos = settings.FREE_PHOTOS_PER_ENTRY if current_user.subscription_tier == "free" else 100
    if len(entry.photos) >= max_photos:
        raise HTTPException(
            status_code=403,
            detail=f"Ліміт фото: {max_photos}. Оновіть до Premium.",
        )

    # FIX: Читаємо файл та перевіряємо розмір
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Файл занадто великий (max 10 МБ)")

    photo_url = await _upload_to_s3(content, file.filename, file.content_type, str(current_user.id))

    # FIX: JSONB mutation detection — треба перепризначити список
    photos = list(entry.photos)
    photos.append({
        "url": photo_url,
        "thumbnail_url": photo_url,
        "taken_at": datetime.now(timezone.utc).isoformat(),
    })
    entry.photos = photos  # SQLAlchemy відстежує тільки якщо об'єкт перепризначено
    await db.commit()

    return {"url": photo_url}


async def _upload_to_s3(content: bytes, filename: str | None, content_type: str | None, user_id: str) -> str:
    """Завантажує файл в S3 та повертає URL."""
    import boto3
    from botocore.exceptions import ClientError

    ext = (filename or "jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    key = f"journal/{user_id}/{uuid4()}.{ext}"

    try:
        s3 = boto3.client(
            "s3",
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.S3_ENDPOINT_URL,
        )
        s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=content,
            ContentType=content_type or "image/jpeg",
        )
    except ClientError as e:
        raise HTTPException(status_code=503, detail=f"Помилка завантаження: {e}")

    if settings.S3_ENDPOINT_URL:
        return f"{settings.S3_ENDPOINT_URL}/{settings.S3_BUCKET}/{key}"
    return f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com/{key}"


async def _check_plant_access(plant_id, user_id, db):
    plant = await db.scalar(
        select(Plant).where(Plant.id == plant_id, Plant.user_id == user_id, Plant.is_deleted == False)
    )
    if not plant:
        raise HTTPException(status_code=404, detail="Рослину не знайдено")
    return plant


async def _get_entry_or_404(entry_id, user_id, db) -> CareJournal:
    entry = await db.scalar(
        select(CareJournal).where(
            CareJournal.id == entry_id,
            CareJournal.user_id == user_id,
            CareJournal.is_deleted == False,
        )
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    return entry
