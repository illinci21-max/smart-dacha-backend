"""
AI Service — діагностика хвороб рослин через Google Vision API.

ВИПРАВЛЕНО:
  - S-02 CRITICAL: SSRF захист — валідація photo_url перед запитом
    (блокуємо приватні IP, локальні адреси, дозволяємо тільки HTTPS з CDN)
"""
import time
import base64
import logging
import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# FIX S-02: дозволені домени для photo_url
# Розширте цей список під свій CDN/S3
ALLOWED_CDN_DOMAINS = (
    "smartdacha-media.",
    "cdn.smartdacha.ua",
    "s3.amazonaws.com",
    "s3.eu-central-1.amazonaws.com",
    "r2.cloudflarestorage.com",
)


def validate_photo_url(url: str) -> None:
    """
    Валідує URL фото перед HTTP запитом.
    ВИПРАВЛЕНО S-02 CRITICAL: захист від SSRF атак.

    Перевіряє:
    1. Схема тільки HTTPS
    2. Домен з дозволеного списку (CDN/S3)
    3. IP не є приватним/loopback/link-local
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL не може бути порожнім")

    if len(url) > 2048:
        raise ValueError("URL занадто довгий")

    parsed = urlparse(url)

    # 1. Тільки HTTPS
    if parsed.scheme != "https":
        raise ValueError("Дозволені лише HTTPS URL")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Невалідний URL — відсутній хост")

    # 2. Перевіряємо дозволені домени
    is_allowed_domain = any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in ALLOWED_CDN_DOMAINS
    )
    if not is_allowed_domain:
        raise ValueError(f"Домен '{hostname}' не входить до списку дозволених CDN")

    # 3. Резолвимо DNS та перевіряємо IP
    try:
        ip_str = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_str)

        if ip.is_private:
            raise ValueError("Доступ до приватних IP заборонено")
        if ip.is_loopback:
            raise ValueError("Доступ до loopback адрес заборонено")
        if ip.is_link_local:
            raise ValueError("Доступ до link-local адрес заборонено")
        if ip.is_reserved:
            raise ValueError("Доступ до зарезервованих IP заборонено")

        # Блокуємо метадані хмарних провайдерів
        # AWS: 169.254.169.254, GCP: 169.254.169.254, Azure: 168.63.129.16
        BLOCKED_IPS = {"169.254.169.254", "168.63.129.16"}
        if ip_str in BLOCKED_IPS:
            raise ValueError("Доступ до хмарних метаданих заборонено")

    except socket.gaierror as e:
        raise ValueError(f"Не вдалося резолвити хост '{hostname}': {e}")


def encode_image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


async def diagnose_plant_photo(
    photo_url: str,
    plant_id: Optional[str] = None,
    crop_diseases: Optional[list] = None,
) -> dict:
    """
    Аналізує фото рослини та повертає список можливих хвороб.
    ВИПРАВЛЕНО S-02: валідація URL перед запитом.
    """
    start = time.time()

    # FIX S-02 CRITICAL: валідуємо URL перед будь-яким HTTP запитом
    validate_photo_url(photo_url)

    if not settings.GOOGLE_VISION_API_KEY:
        return _mock_diagnosis(crop_diseases)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            photo_resp = await client.get(photo_url)
            photo_resp.raise_for_status()
            image_b64 = encode_image_to_base64(photo_resp.content)

        vision_url = (
            f"https://vision.googleapis.com/v1/images:annotate"
            f"?key={settings.GOOGLE_VISION_API_KEY}"
        )
        payload = {
            "requests": [
                {
                    "image": {"content": image_b64},
                    "features": [
                        {"type": "LABEL_DETECTION", "maxResults": 20},
                        {"type": "IMAGE_PROPERTIES"},
                        {"type": "OBJECT_LOCALIZATION", "maxResults": 10},
                    ],
                }
            ]
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            vision_resp = await client.post(vision_url, json=payload)
            vision_resp.raise_for_status()
            vision_data = vision_resp.json()

        results = _parse_vision_response(vision_data, crop_diseases or [])
        elapsed_ms = int((time.time() - start) * 1000)

        return {
            "results": results,
            "model_version": "google_vision_v1",
            "processing_time_ms": elapsed_ms,
        }

    except ValueError:
        raise  # Re-raise validation errors
    except Exception as e:
        logger.error(f"Vision API error: {e}")
        raise


def _parse_vision_response(vision_data: dict, known_diseases: list) -> list:
    labels = []
    for resp in vision_data.get("responses", []):
        for label in resp.get("labelAnnotations", []):
            labels.append({
                "description": label.get("description", "").lower(),
                "score": label.get("score", 0.0),
            })

    results = []
    disease_keywords = {
        "late_blight": ["blight", "phytophthora", "rot", "brown spot"],
        "powdery_mildew": ["mildew", "white powder", "fungus"],
        "aphids": ["aphid", "louse", "insect", "pest"],
        "yellow_leaf": ["yellow", "chlorosis", "yellowing"],
        "rust": ["rust", "orange", "pustule"],
    }

    detected_diseases = set()
    for label in labels:
        desc = label["description"]
        for disease_id, keywords in disease_keywords.items():
            if any(kw in desc for kw in keywords) and disease_id not in detected_diseases:
                detected_diseases.add(disease_id)
                disease_info = next(
                    (d for d in known_diseases if d.get("id") == disease_id),
                    {"id": disease_id, "name": disease_id.replace("_", " ").title()}
                )
                results.append({
                    "disease_id": disease_id,
                    "disease_name": disease_info.get("name", disease_id),
                    "confidence": round(label["score"], 3),
                    "severity": _estimate_severity(label["score"]),
                    "recommendations": _get_recommendations(disease_id),
                    "bounding_box": None,
                })

    return sorted(results, key=lambda x: x["confidence"], reverse=True)


def _estimate_severity(confidence: float) -> str:
    if confidence > 0.85:
        return "severe"
    elif confidence > 0.65:
        return "moderate"
    return "mild"


def _get_recommendations(disease_id: str) -> list[str]:
    recs = {
        "late_blight": [
            "Видаліть уражені листки та плоди",
            "Обробіть мідним купоросом (0.1%) або Ридомілом Голд",
            "Зменшіть вологість, уникайте поливу по листку",
            "Повторіть обробку через 7-10 днів",
        ],
        "powdery_mildew": [
            "Обробіть розчином соди (5г/1л) або фунгіцидом Топаз",
            "Покращіть вентиляцію між рослинами",
            "Уникайте надлишкового азотного підживлення",
        ],
        "aphids": [
            "Обробіть мильним розчином або інсектицидом",
            "Залучіть корисних комах (сонечка)",
            "Видаліть найбільш уражені частини",
        ],
        "yellow_leaf": [
            "Перевірте pH ґрунту (оптимум 6.0-7.0)",
            "Підживіть хелатом заліза або комплексним добривом",
            "Перевірте режим поливу",
        ],
        "rust": [
            "Видаліть уражені листки",
            "Обробіть фунгіцидом на основі пропіконазолу",
            "Покращіть дренаж ґрунту",
        ],
    }
    return recs.get(disease_id, ["Зверніться до агронома для детальної консультації"])


def _mock_diagnosis(crop_diseases: Optional[list]) -> dict:
    """Мок для розробки без Google Vision API."""
    return {
        "results": [
            {
                "disease_id": "demo_result",
                "disease_name": "Демо результат (API ключ не налаштовано)",
                "confidence": 0.75,
                "severity": "moderate",
                "recommendations": ["Налаштуйте GOOGLE_VISION_API_KEY в .env"],
                "bounding_box": None,
            }
        ],
        "model_version": "mock_v1",
        "processing_time_ms": 42,
    }
