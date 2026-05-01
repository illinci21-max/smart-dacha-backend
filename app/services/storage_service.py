"""
Storage Service — завантаження файлів у S3-сумісне сховище.

ВИПРАВЛЕНО:
  - S-03 CRITICAL: Виправлено назви Settings полів:
    settings.S3_ACCESS_KEY  -> settings.AWS_ACCESS_KEY_ID
    settings.S3_SECRET_KEY  -> settings.AWS_SECRET_ACCESS_KEY
    settings.S3_BUCKET_NAME -> settings.S3_BUCKET
    settings.CDN_BASE_URL   -> генерується з S3_BUCKET + S3_REGION
  - Додано CDN_BASE_URL до Settings (через config.py)
  - Додано перевірку типу файлу (magic bytes) для безпеки (S-11)
"""
import mimetypes
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import UploadFile, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

# FIX S-11: дозволені MIME типи для завантаження фото
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
}

# FIX S-11: магічні байти для перевірки реального формату файлу
MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # потребує додаткової перевірки WEBP
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _get_cdn_base_url() -> str:
    """Повертає CDN базовий URL."""
    # FIX S-03: використовуємо правильні назви з Settings
    if settings.S3_ENDPOINT_URL:
        # MinIO або кастомний S3
        return f"{settings.S3_ENDPOINT_URL}/{settings.S3_BUCKET}"
    return f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com"


def validate_image_file(file: UploadFile, content: bytes) -> None:
    """
    Валідує файл зображення за content-type та magic bytes.
    FIX S-11: перевірка magic bytes, не тільки Content-Type.
    """
    # Перевірка розміру
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Файл занадто великий. Максимум: {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB"
        )

    # Перевірка Content-Type
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Непідтримуваний тип файлу '{content_type}'. Дозволено: JPEG, PNG, WebP"
        )

    # FIX S-11: Перевірка magic bytes (реальний формат файлу)
    detected_type = None
    for magic, mime in MAGIC_BYTES.items():
        if content[:len(magic)] == magic:
            detected_type = mime
            break

    # WEBP: перевіряємо WEBP після RIFF
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        detected_type = "image/webp"
    elif content[:4] == b"RIFF":
        detected_type = None  # RIFF але не WEBP — підозрілий файл

    if detected_type is None:
        raise HTTPException(
            status_code=415,
            detail="Файл не є зображенням. Перевірте формат файлу."
        )

    # Content-Type має відповідати реальному формату
    if detected_type == "image/jpeg" and content_type not in ("image/jpeg", "image/jpg"):
        raise HTTPException(status_code=415, detail="Content-Type не відповідає вмісту файлу")


async def upload_file_to_s3(
    file: UploadFile,
    folder: str = "uploads",
    validate: bool = True,
) -> dict:
    """
    Завантажує файл у S3 та повертає dict з URL та метаданими.
    ВИПРАВЛЕНО S-03: правильні назви settings полів.
    ВИПРАВЛЕНО S-11: валідація magic bytes.
    """
    content = await file.read()

    # Валідація файлу перед завантаженням
    if validate:
        validate_image_file(file, content)

    ext = mimetypes.guess_extension(file.content_type or "image/jpeg") or ".jpg"
    # Нормалізуємо розширення (guess_extension може повертати .jpe замість .jpg)
    if ext in (".jpe", ".jfif"):
        ext = ".jpg"

    filename = f"{folder}/{uuid.uuid4()}{ext}"

    try:
        import aioboto3
        session = aioboto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,       # FIX S-03
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,  # FIX S-03
            region_name=settings.S3_REGION,
        )

        async with session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,  # None для AWS, URL для MinIO
        ) as s3:
            await s3.put_object(
                Bucket=settings.S3_BUCKET,    # FIX S-03: S3_BUCKET не S3_BUCKET_NAME
                Key=filename,
                Body=content,
                ContentType=file.content_type,
                # ContentDisposition="inline",  # Відкривати в браузері
            )

        cdn_base = _get_cdn_base_url()
        cdn_url = f"{cdn_base}/{filename}"
        thumbnail_url = f"{cdn_url}?w=400&h=400&fit=crop"

        logger.info(f"Uploaded file: {filename} ({len(content)} bytes)")

        return {
            "url": cdn_url,
            "thumbnail_url": thumbnail_url,
            "filename": filename,
            "size_bytes": len(content),
            "content_type": file.content_type,
            "taken_at": datetime.now(timezone.utc).isoformat(),
        }

    except ImportError:
        logger.error("aioboto3 not installed. Run: pip install aioboto3")
        raise HTTPException(status_code=500, detail="Storage service not configured")
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        raise HTTPException(status_code=500, detail="Помилка завантаження файлу")


async def delete_file_from_s3(filename: str) -> bool:
    """Видаляє файл з S3."""
    try:
        import aioboto3
        session = aioboto3.Session(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.S3_REGION,
        )
        async with session.client("s3", endpoint_url=settings.S3_ENDPOINT_URL) as s3:
            await s3.delete_object(Bucket=settings.S3_BUCKET, Key=filename)
        return True
    except Exception as e:
        logger.error(f"S3 delete failed for {filename}: {e}")
        return False
