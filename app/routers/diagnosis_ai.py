"""
AI Diagnosis Router — plant disease identification via Gemini + PlantNet.

Endpoints:
  POST /diagnose-ai/analyze   — upload photo, get AI diagnosis
  GET  /diagnose-ai/history   — user's diagnosis history
"""
import base64
import logging
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, UploadFile, File
import httpx

from app.dependencies import get_current_user
from app.models.user import User
from app.config import settings
from app.services.upload_validation import validate_image_upload

router = APIRouter(prefix="/diagnose-ai", tags=["ai-diagnosis"])
logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
_PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/all"

_GEMINI_PROMPT = """Ти — експерт-агроном. Проаналізуй фото рослини та визнач:
1. Назва рослини (українською та латиною)
2. Виявлені хвороби або проблеми (якщо є)
3. Стадія ураження (рання/середня/критична)
4. Конкретні рекомендації з лікування
5. Профілактика на майбутнє

Відповідай ТІЛЬКИ українською. Якщо рослина здорова — скажи це.
Якщо на фото не рослина — скажи що не можеш проаналізувати.

Формат відповіді (JSON):
{
  "plant_name": "Томат (Solanum lycopersicum)",
  "is_healthy": false,
  "disease_name": "Фітофтороз",
  "severity": "середня",
  "confidence": 85,
  "description": "Опис симптомів...",
  "treatment": ["Крок 1...", "Крок 2..."],
  "prevention": ["Порада 1...", "Порада 2..."]
}"""


# ── Gemini API ────────────────────────────────────────────────────────────────

async def _analyze_with_gemini(image_bytes: bytes, mime_type: str) -> dict | None:
    """Call Google Gemini with the image. Returns parsed JSON or None."""
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not configured")
        return None

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "contents": [{
            "parts": [
                {"text": _GEMINI_PROMPT},
                {"inline_data": {"mime_type": mime_type, "data": b64}},
            ]
        }],
        "generationConfig": {
            "temperature": 0.3,
            "response_mime_type": "application/json",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_GEMINI_URL}?key={settings.GEMINI_API_KEY}",
                json=payload,
            )
        if resp.status_code != 200:
            logger.error("Gemini API error %d: %s", resp.status_code, resp.text[:300])
            return None

        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]

        # Parse JSON from response
        import json
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        result = json.loads(text)
        result["source"] = "gemini"
        logger.info("Gemini diagnosis: %s (confidence: %s%%)",
                     result.get("disease_name", "healthy"), result.get("confidence", "?"))
        return result

    except Exception as ex:
        logger.exception("Gemini analysis failed: %s", ex)
        return None


# ── PlantNet API ──────────────────────────────────────────────────────────────

async def _identify_with_plantnet(image_bytes: bytes) -> dict | None:
    """Call PlantNet API. Returns simplified result or None."""
    if not settings.PLANTNET_API_KEY:
        logger.warning("PLANTNET_API_KEY not configured")
        return None

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                _PLANTNET_URL,
                params={"api-key": settings.PLANTNET_API_KEY, "lang": "uk"},
                files={"images": ("photo.jpg", image_bytes, "image/jpeg")},
                data={"organs": "leaf"},
            )
        if resp.status_code != 200:
            logger.error("PlantNet error %d: %s", resp.status_code, resp.text[:300])
            return None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        best = results[0]
        species = best.get("species", {})
        score = best.get("score", 0)

        return {
            "plant_name": species.get("commonNames", ["Невідома рослина"])[0]
            if species.get("commonNames") else species.get("scientificNameWithoutAuthor", "?"),
            "scientific_name": species.get("scientificNameWithoutAuthor", ""),
            "confidence": round(score * 100),
            "family": species.get("family", {}).get("scientificNameWithoutAuthor", ""),
            "source": "plantnet",
        }

    except Exception as ex:
        logger.exception("PlantNet identification failed: %s", ex)
        return None


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_photo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Upload a plant photo and get AI diagnosis + identification."""
    # Validate
    image_bytes = await file.read()
    validated_upload = validate_image_upload(
        image_bytes,
        file.content_type,
        max_size_bytes=MAX_FILE_SIZE,
    )

    logger.info("AI diagnosis request from user %s, image %d bytes, type %s",
                current_user.id, len(image_bytes), validated_upload.content_type)

    # Run both APIs in parallel
    import asyncio
    gemini_task = asyncio.create_task(_analyze_with_gemini(image_bytes, validated_upload.content_type))
    plantnet_task = asyncio.create_task(_identify_with_plantnet(image_bytes))

    gemini_result = await gemini_task
    plantnet_result = await plantnet_task

    # Build response
    response = {
        "id": str(uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gemini": gemini_result,
        "plantnet": plantnet_result,
    }

    # Compose summary
    if gemini_result:
        response["summary"] = {
            "plant_name": gemini_result.get("plant_name", "Невідомо"),
            "is_healthy": gemini_result.get("is_healthy", True),
            "disease_name": gemini_result.get("disease_name"),
            "severity": gemini_result.get("severity"),
            "confidence": gemini_result.get("confidence", 0),
            "description": gemini_result.get("description", ""),
            "treatment": gemini_result.get("treatment", []),
            "prevention": gemini_result.get("prevention", []),
            "source": "gemini",
        }
    elif plantnet_result:
        response["summary"] = {
            "plant_name": plantnet_result.get("plant_name", "Невідомо"),
            "is_healthy": True,
            "disease_name": None,
            "severity": None,
            "confidence": plantnet_result.get("confidence", 0),
            "description": f"Ідентифіковано: {plantnet_result.get('scientific_name', '')} "
                          f"(родина: {plantnet_result.get('family', '')})",
            "treatment": [],
            "prevention": [],
            "source": "plantnet",
        }
    else:
        response["summary"] = {
            "plant_name": "Не вдалося визначити",
            "is_healthy": True,
            "disease_name": None,
            "severity": None,
            "confidence": 0,
            "description": "API недоступні. Перевірте ключі GEMINI_API_KEY та PLANTNET_API_KEY.",
            "treatment": [],
            "prevention": [],
            "source": "none",
        }

    return response