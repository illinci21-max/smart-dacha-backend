"""
Diagnostics Router — AI-діагностика хвороб рослин.
Free: 3 запити/місяць. Premium: необмежено.
"""
from uuid import UUID, uuid4
from datetime import datetime, timezone, date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import get_current_user, require_premium
from app.models.user import User
from app.models.ai_diagnosis import AIDiagnosis
from app.models.plant import Plant
from app.models.crop import CropCatalog
from app.schemas.diagnosis import DiagnosisResponse, DiagnosisFeedbackRequest
from app.services.ai_service import diagnose_plant_photo
from app.config import settings

router = APIRouter(prefix="/diagnose", tags=["diagnostics"])

# FIX: максимальний розмір файлу 10 МБ
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def _check_diagnosis_limit(user: User, db: AsyncSession):
    """Перевіряє місячний ліміт діагнозів для Free-користувачів."""
    if user.subscription_tier != "free":
        return

    today = date.today()
    first_day = datetime(today.year, today.month, 1, tzinfo=timezone.utc)

    count = await db.scalar(
        select(func.count()).where(
            AIDiagnosis.user_id == user.id,
            AIDiagnosis.created_at >= first_day,
        )
    )
    if count >= settings.FREE_DIAGNOSES_PER_MONTH:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "diagnosis_limit_reached",
                "used": count,
                "limit": settings.FREE_DIAGNOSES_PER_MONTH,
                "message": f"Ліміт {settings.FREE_DIAGNOSES_PER_MONTH} діагнози/місяць для Free. Оновіть до Premium.",
            },
        )


@router.post("", response_model=DiagnosisResponse, status_code=202)
async def create_diagnosis(
    file: UploadFile = File(...),
    plant_id: UUID | None = Form(default=None),
    photo_taken_at: datetime | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_diagnosis_limit(current_user, db)

    # FIX: Валідація типу файлу
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Підтримуються тільки: {', '.join(ALLOWED_CONTENT_TYPES)}"
        )

    # FIX: Обмеження розміру файлу
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл занадто великий. Максимум: {MAX_FILE_SIZE_BYTES // 1024 // 1024} МБ"
        )

    # FIX: Перевірка доступу до рослини перед завантаженням в S3
    crop_diseases = []
    if plant_id:
        plant = await db.scalar(
            select(Plant).where(Plant.id == plant_id, Plant.user_id == current_user.id)
        )
        if not plant:
            raise HTTPException(status_code=404, detail="Рослину не знайдено")
        crop = await db.get(CropCatalog, plant.crop_id)
        if crop:
            crop_diseases = crop.common_diseases or []

    # Завантаження в S3
    import boto3
    from botocore.exceptions import ClientError

    ext = (file.filename or "jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    photo_key = f"diagnoses/{current_user.id}/{uuid4()}.{ext}"

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
            Key=photo_key,
            Body=content,
            ContentType=file.content_type or "image/jpeg",
        )
    except ClientError as e:
        raise HTTPException(status_code=503, detail=f"Помилка завантаження файлу: {e}")

    if settings.S3_ENDPOINT_URL:
        photo_url = f"{settings.S3_ENDPOINT_URL}/{settings.S3_BUCKET}/{photo_key}"
    else:
        photo_url = f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com/{photo_key}"

    diagnosis = AIDiagnosis(
        user_id=current_user.id,
        plant_id=plant_id,
        photo_url=photo_url,
        photo_taken_at=photo_taken_at,
        status="processing",
    )
    db.add(diagnosis)
    await db.commit()
    await db.refresh(diagnosis)

    try:
        ai_result = await diagnose_plant_photo(
            photo_url, str(plant_id) if plant_id else None, crop_diseases
        )
        diagnosis.results = ai_result["results"]
        diagnosis.model_version = ai_result["model_version"]
        diagnosis.processing_time_ms = ai_result["processing_time_ms"]
        diagnosis.status = "completed"
        diagnosis.completed_at = datetime.now(timezone.utc)
    except Exception as e:
        diagnosis.status = "failed"
        diagnosis.error_message = str(e)[:500]  # FIX: обмежено довжину помилки

    await db.commit()
    await db.refresh(diagnosis)
    return diagnosis


@router.get("/history/all", response_model=list[DiagnosisResponse])
async def get_diagnosis_history(
    current_user: User = Depends(require_premium("diagnosis_history")),
    db: AsyncSession = Depends(get_db),
):
    """Повна історія діагнозів (тільки Premium)."""
    # FIX: цей маршрут має бути ПЕРЕД /{diagnosis_id} інакше FastAPI матчить "history" як UUID
    result = await db.execute(
        select(AIDiagnosis)
        .where(AIDiagnosis.user_id == current_user.id)
        .order_by(AIDiagnosis.created_at.desc())
        .limit(100)
    )
    return result.scalars().all()


@router.get("/{diagnosis_id}", response_model=DiagnosisResponse)
async def get_diagnosis(
    diagnosis_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _get_diagnosis_or_404(diagnosis_id, current_user.id, db)


@router.post("/{diagnosis_id}/feedback", status_code=204)
async def submit_feedback(
    diagnosis_id: UUID,
    data: DiagnosisFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    valid_feedbacks = {"correct", "incorrect", "unsure"}
    if data.feedback not in valid_feedbacks:
        raise HTTPException(status_code=422, detail=f"feedback має бути одним з: {valid_feedbacks}")

    diagnosis = await _get_diagnosis_or_404(diagnosis_id, current_user.id, db)
    diagnosis.user_feedback = data.feedback
    await db.commit()


async def _get_diagnosis_or_404(diagnosis_id, user_id, db) -> AIDiagnosis:
    d = await db.scalar(
        select(AIDiagnosis).where(AIDiagnosis.id == diagnosis_id, AIDiagnosis.user_id == user_id)
    )
    if not d:
        raise HTTPException(status_code=404, detail="Діагноз не знайдено")
    return d
