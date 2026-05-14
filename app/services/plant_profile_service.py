"""
PlantProfileService — сервісний шар для пошуку та створення агро-профілів.

Стратегія пошуку (кожен крок — fallback для попереднього):
  1. Точний збіг по назві в plant_profiles
  2. Нечіткий пошук (trigram similarity ≥ 0.4) — уникає дублів
  3. Пошук у crop_catalog (існуючий каталог культур)
  4. Gemini 2.5 Flash → генерація FAO-56 профілю → збереження в БД

Мінімізація звернень до Gemini:
  - Нормалізація назви: "Томати чері" → "томат черрі" (lowercase, trim)
  - Trigram similarity знаходить "Помідор" коли шукають "Томат"
  - Один запит Gemini → назавжди у БД для всіх користувачів
"""
import json
import logging
import re
import unicodedata
from datetime import date
from typing import Any

import httpx
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.gemini_usage import record_gemini_usage
from app.services.redis_service import get_cache_redis

logger = logging.getLogger(__name__)

_DEFAULT_PROFILE = {
    "emoji": "🌱",
    "source": "default",
    "description": None,
    "kc_initial": 0.40,
    "kc_mid": 1.05,
    "kc_end": 0.70,
    "initial_days": 20,
    "development_days": 30,
    "mid_season_days": 35,
    "late_season_days": 20,
    "root_depth_initial_cm": 10,
    "root_depth_max_cm": 50,
    "field_capacity_mm": 180,
    "wilting_point_mm": 55,
    "critical_depletion": 0.50,
    "t_min_growth": 8,
    "t_optimal_min": 18,
    "t_optimal_max": 28,
    "t_max_growth": 38,
    "frost_tolerance": 0,
    "nitrogen": 2.0,
    "phosphorus": 1.0,
    "potassium": 2.0,
    "magnesium": 0.3,
    "calcium": 0.5,
    "sus_late_blight": 0.3,
    "sus_powdery_mildew": 0.3,
    "sus_downy_mildew": 0.3,
    "sus_botrytis": 0.2,
    "days_to_harvest_min": 60,
    "days_to_harvest_max": 90,
    "disease_protection_adaptation_days": 5,
    "disease_protection_early_symptom_days": 2,
    "biofungicide_allowed_from_day": 0,
    "chemical_fungicide_allowed_from_day": 5,
    "copper_fungicide_allowed_from_day": 7,
    "max_spray_temp_c": 28,
    "avoid_spray_before_rain_hours": 6,
    "cold_stress_threshold_c": None,
    "frost_critical_threshold_c": None,
}

_ALIASES = {
    "помідор": "томат",
    "помідори": "томат",
    "помидор": "томат",
    "помидоры": "томат",
    "томати": "томат",
    "tomato": "томат",
    "tomatoes": "томат",
    "картошка": "картопля",
    "картофель": "картопля",
    "potato": "картопля",
    "potatoes": "картопля",
    "огурец": "огірок",
    "огурцы": "огірок",
    "огірки": "огірок",
    "cucumber": "огірок",
    "cucumbers": "огірок",
    "перець солодкий": "перець",
    "болгарський перець": "перець",
    "pepper": "перець",
    "peppers": "перець",
    "полуниця": "суниця",
    "strawberry": "суниця",
}

_CURATED_PROFILES: dict[str, dict[str, Any]] = {
    "томат": {
        "emoji": "🍅",
        "category": "Овочі",
        "description": "Теплолюбна овочева культура з високою потребою у рівномірному поливі під час цвітіння та плодоношення.",
        "kc_initial": 0.60,
        "kc_mid": 1.15,
        "kc_end": 0.80,
        "initial_days": 30,
        "development_days": 40,
        "mid_season_days": 45,
        "late_season_days": 30,
        "root_depth_initial_cm": 15,
        "root_depth_max_cm": 70,
        "critical_depletion": 0.40,
        "t_min_growth": 10,
        "t_optimal_min": 18,
        "t_optimal_max": 27,
        "t_max_growth": 35,
        "frost_tolerance": 1,
        "nitrogen": 2.5,
        "phosphorus": 1.0,
        "potassium": 3.0,
        "calcium": 0.8,
        "sus_late_blight": 0.85,
        "sus_botrytis": 0.55,
        "days_to_harvest_min": 70,
        "days_to_harvest_max": 120,
    },
    "огірок": {
        "emoji": "🥒",
        "category": "Овочі",
        "description": "Вологолюбна теплолюбна культура з поверхневішою кореневою системою та високою чутливістю до холоду.",
        "kc_initial": 0.60,
        "kc_mid": 1.00,
        "kc_end": 0.75,
        "initial_days": 20,
        "development_days": 30,
        "mid_season_days": 40,
        "late_season_days": 15,
        "root_depth_initial_cm": 10,
        "root_depth_max_cm": 45,
        "critical_depletion": 0.35,
        "t_min_growth": 12,
        "t_optimal_min": 20,
        "t_optimal_max": 30,
        "t_max_growth": 35,
        "frost_tolerance": 2,
        "nitrogen": 2.0,
        "phosphorus": 0.8,
        "potassium": 2.6,
        "sus_downy_mildew": 0.85,
        "sus_powdery_mildew": 0.65,
        "days_to_harvest_min": 45,
        "days_to_harvest_max": 70,
    },
    "картопля": {
        "emoji": "🥔",
        "category": "Овочі",
        "description": "Бульбова культура з підвищеною потребою у волозі під час бутонізації та формування бульб.",
        "kc_initial": 0.50,
        "kc_mid": 1.15,
        "kc_end": 0.75,
        "initial_days": 25,
        "development_days": 30,
        "mid_season_days": 45,
        "late_season_days": 30,
        "root_depth_initial_cm": 15,
        "root_depth_max_cm": 60,
        "critical_depletion": 0.40,
        "t_min_growth": 7,
        "t_optimal_min": 15,
        "t_optimal_max": 24,
        "t_max_growth": 30,
        "frost_tolerance": -1,
        "nitrogen": 2.2,
        "phosphorus": 1.0,
        "potassium": 3.2,
        "sus_late_blight": 0.9,
        "days_to_harvest_min": 80,
        "days_to_harvest_max": 120,
    },
    "перець": {
        "emoji": "🌶️",
        "category": "Овочі",
        "description": "Теплолюбна культура з повільним стартом росту та високою чутливістю до холодних ночей.",
        "kc_initial": 0.60,
        "kc_mid": 1.05,
        "kc_end": 0.90,
        "initial_days": 30,
        "development_days": 35,
        "mid_season_days": 45,
        "late_season_days": 25,
        "root_depth_initial_cm": 10,
        "root_depth_max_cm": 55,
        "critical_depletion": 0.40,
        "t_min_growth": 12,
        "t_optimal_min": 20,
        "t_optimal_max": 30,
        "t_max_growth": 35,
        "frost_tolerance": 2,
        "nitrogen": 2.0,
        "phosphorus": 0.9,
        "potassium": 2.8,
        "sus_botrytis": 0.45,
        "days_to_harvest_min": 70,
        "days_to_harvest_max": 110,
    },
}

_FLOAT_RANGES = {
    "kc_initial": (0.15, 0.85),
    "kc_mid": (0.45, 1.35),
    "kc_end": (0.20, 1.15),
    "root_depth_initial_cm": (3, 80),
    "root_depth_max_cm": (10, 250),
    "field_capacity_mm": (60, 320),
    "wilting_point_mm": (20, 180),
    "critical_depletion": (0.20, 0.75),
    "t_min_growth": (-5, 20),
    "t_optimal_min": (5, 30),
    "t_optimal_max": (10, 40),
    "t_max_growth": (20, 50),
    "frost_tolerance": (-35, 8),
    "nitrogen": (0, 8),
    "phosphorus": (0, 5),
    "potassium": (0, 8),
    "magnesium": (0, 3),
    "calcium": (0, 5),
    "sus_late_blight": (0, 1),
    "sus_powdery_mildew": (0, 1),
    "sus_downy_mildew": (0, 1),
    "sus_botrytis": (0, 1),
    "max_spray_temp_c": (18, 35),
}

_INT_RANGES = {
    "initial_days": (5, 80),
    "development_days": (5, 90),
    "mid_season_days": (5, 120),
    "late_season_days": (5, 90),
    "days_to_harvest_min": (15, 365),
    "days_to_harvest_max": (20, 450),
    "disease_protection_adaptation_days": (0, 21),
    "disease_protection_early_symptom_days": (0, 14),
    "biofungicide_allowed_from_day": (0, 14),
    "chemical_fungicide_allowed_from_day": (0, 21),
    "copper_fungicide_allowed_from_day": (0, 21),
    "avoid_spray_before_rain_hours": (0, 48),
}


def _normalize_name(name: str) -> str:
    """
    Нормалізація назви рослини для дедуплікації.
    "  Томати ЧЕРРІ  " → "томат черрі"
    Видаляє множину, зайві пробіли, приводить до lowercase.
    """
    s = unicodedata.normalize("NFKC", name or "").strip().lower()
    s = s.replace("ё", "е").replace("ґ", "г")
    s = re.sub(r"[^\w\s\-іїєа-яa-z]", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s)
    s = s.strip(" -")
    if s in _ALIASES:
        return _ALIASES[s]
    words = [_ALIASES.get(word, word) for word in s.split()]
    s = " ".join(words)
    if s in _ALIASES:
        return _ALIASES[s]
    # Обережна нормалізація множини: тільки типові закінчення, без агресивного "ати".
    replacements = {
        "огірки": "огірок",
        "помідори": "помідор",
        "томати": "томат",
        "кабачки": "кабачок",
        "буряки": "буряк",
    }
    if s in replacements:
        return _ALIASES.get(replacements[s], replacements[s])
    for suffix in ["ові", "еві", "і", "и"]:
        if len(s) > len(suffix) + 4 and s.endswith(suffix):
            candidate = s[: -len(suffix)]
            return _ALIASES.get(candidate, candidate)
    return s


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_float(value: Any, default: float) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _with_defaults(data: dict | None, name: str, category: str, source: str) -> dict:
    profile = {**_DEFAULT_PROFILE, **(data or {})}
    profile["name"] = str(profile.get("name") or name).strip() or name
    profile["category"] = str(profile.get("category") or category or "Овочі")
    profile["source"] = source
    return profile


def sanitize_profile_data(
    data: dict | None,
    name: str,
    category: str,
    source: str,
) -> dict:
    """Validate Gemini/catalog/curated data before it can influence agro analysis."""
    profile = _with_defaults(data, name, category, source)
    warnings: list[str] = []

    for key, (low, high) in _FLOAT_RANGES.items():
        raw = _as_float(profile.get(key), float(_DEFAULT_PROFILE[key]))
        value = _clamp(raw, low, high)
        if value != raw:
            warnings.append(f"{key}: {raw} -> {value}")
        profile[key] = value

    for key, (low, high) in _INT_RANGES.items():
        raw = _as_int(profile.get(key), int(_DEFAULT_PROFILE[key]))
        value = int(_clamp(raw, low, high))
        if value != raw:
            warnings.append(f"{key}: {raw} -> {value}")
        profile[key] = value

    for key, (low, high) in {
        "cold_stress_threshold_c": (-15, 15),
        "frost_critical_threshold_c": (-35, 8),
    }.items():
        raw_value = profile.get(key)
        if raw_value is None or raw_value == "":
            profile[key] = None
            continue
        raw = _as_float(raw_value, float(_DEFAULT_PROFILE["frost_tolerance"]))
        value = _clamp(raw, low, high)
        if value != raw:
            warnings.append(f"{key}: {raw} -> {value}")
        profile[key] = value

    if profile["root_depth_initial_cm"] > profile["root_depth_max_cm"]:
        warnings.append("root_depth_initial_cm capped to root_depth_max_cm")
        profile["root_depth_initial_cm"] = profile["root_depth_max_cm"]

    if profile["wilting_point_mm"] >= profile["field_capacity_mm"]:
        profile["wilting_point_mm"] = max(20, profile["field_capacity_mm"] * 0.35)
        warnings.append("wilting_point_mm recalculated below field_capacity_mm")

    if profile["t_optimal_min"] > profile["t_optimal_max"]:
        profile["t_optimal_min"], profile["t_optimal_max"] = (
            profile["t_optimal_max"],
            profile["t_optimal_min"],
        )
        warnings.append("optimal temperature range swapped")

    if profile["t_min_growth"] > profile["t_optimal_min"]:
        profile["t_min_growth"] = profile["t_optimal_min"] - 2
        warnings.append("t_min_growth lowered below optimal range")

    if profile["t_max_growth"] < profile["t_optimal_max"]:
        profile["t_max_growth"] = profile["t_optimal_max"] + 3
        warnings.append("t_max_growth raised above optimal range")

    if profile["days_to_harvest_min"] > profile["days_to_harvest_max"]:
        profile["days_to_harvest_min"], profile["days_to_harvest_max"] = (
            profile["days_to_harvest_max"],
            profile["days_to_harvest_min"],
        )
        warnings.append("harvest day range swapped")

    profile["profile_confidence"] = {
        "curated": 95,
        "catalog": 82,
        "gemini": 70,
        "default": 45,
    }.get(source, 60) - min(25, len(warnings) * 5)
    profile["confidence"] = profile["profile_confidence"]
    profile["validation_warnings"] = warnings
    return profile


def _profile_kwargs(profile: dict) -> dict:
    fields = [
        "name", "name_normalized", "category", "emoji", "source", "description",
        "confidence", "validation_warnings",
        "kc_initial", "kc_mid", "kc_end",
        "initial_days", "development_days", "mid_season_days", "late_season_days",
        "root_depth_initial_cm", "root_depth_max_cm",
        "field_capacity_mm", "wilting_point_mm", "critical_depletion",
        "t_min_growth", "t_optimal_min", "t_optimal_max", "t_max_growth", "frost_tolerance",
        "nitrogen", "phosphorus", "potassium", "magnesium", "calcium",
        "sus_late_blight", "sus_powdery_mildew", "sus_downy_mildew", "sus_botrytis",
        "days_to_harvest_min", "days_to_harvest_max",
        "disease_protection_adaptation_days", "disease_protection_early_symptom_days",
        "biofungicide_allowed_from_day", "chemical_fungicide_allowed_from_day",
        "copper_fungicide_allowed_from_day", "max_spray_temp_c",
        "avoid_spray_before_rain_hours", "cold_stress_threshold_c",
        "frost_critical_threshold_c",
    ]
    return {field: profile.get(field) for field in fields if field in profile}


async def _save_profile(profile_data: dict, db: AsyncSession):
    from app.models.plant_profile import PlantProfile

    profile_data["name_normalized"] = _normalize_name(profile_data["name"])
    profile = PlantProfile(**_profile_kwargs(profile_data))
    db.add(profile)
    try:
        await db.commit()
        await db.refresh(profile)
    except Exception:
        await db.rollback()
        profile = await find_profile_exact(profile_data["name"], db)
    return profile


# ══════════════════════════════════════════════════════════════════════════════
# FUZZY SEARCH
# ══════════════════════════════════════════════════════════════════════════════

async def find_profile_exact(name: str, db: AsyncSession):
    """Крок 1: точний збіг по назві."""
    from app.models.plant_profile import PlantProfile
    normalized = _normalize_name(name)
    return await db.scalar(
        select(PlantProfile).where(
            or_(
                PlantProfile.name == name,
                PlantProfile.name_normalized == normalized,
            )
        )
    )


async def find_profile_fuzzy(name: str, db: AsyncSession, threshold: float = 0.35):
    """
    Крок 2: нечіткий пошук через pg_trgm similarity.
    Знаходить: "Помідор" → "Томат", "Картошка" → "Картопля".
    Потребує CREATE EXTENSION IF NOT EXISTS pg_trgm; (виконується в init.sql).
    """
    from app.models.plant_profile import PlantProfile

    normalized = _normalize_name(name)

    # Спершу пробуємо по нормалізованій назві
    row = await db.scalar(
        select(PlantProfile).where(PlantProfile.name_normalized == normalized)
    )
    if row:
        return row

    # Trigram similarity (потребує розширення pg_trgm)
    try:
        stmt = (
            select(PlantProfile)
            .where(func.similarity(PlantProfile.name_normalized, normalized) >= threshold)
            .order_by(func.similarity(PlantProfile.name_normalized, normalized).desc())
            .limit(1)
        )
        return await db.scalar(stmt)
    except Exception as e:
        # pg_trgm може бути не встановлено — fallback на ILIKE
        logger.debug("pg_trgm not available, falling back to ILIKE: %s", e)
        stmt = (
            select(PlantProfile)
            .where(
                or_(
                    PlantProfile.name.ilike(f"%{name}%"),
                    PlantProfile.name_normalized.ilike(f"%{normalized}%"),
                )
            )
            .limit(1)
        )
        return await db.scalar(stmt)


async def find_in_crop_catalog(name: str, db: AsyncSession):
    """
    Крок 3: пошук у існуючому crop_catalog (таблиця з каталогу культур).
    Якщо знайдено — створюємо PlantProfile з базовими даними.
    """
    from app.models.crop import CropCatalog
    from app.models.plant_profile import PlantProfile

    crop = await db.scalar(
        select(CropCatalog).where(
            CropCatalog.name_uk.ilike(f"%{name}%")
        ).limit(1)
    )
    if not crop:
        return None

    # Створюємо профіль з даних каталогу, але пропускаємо через ті ж guardrails.
    data = {
        "name": name,
        "name_normalized": _normalize_name(name),
        "category": crop.category or "Овочі",
        "emoji": crop.emoji or "🌱",
        "source": "catalog",
        "description": crop.description,
        "t_min_growth": float(crop.t_base or 10),
        "t_optimal_min": float(crop.t_optimal_min or 18),
        "t_optimal_max": float(crop.t_optimal_max or 28),
    }
    if crop.drought_tolerance:
        data["critical_depletion"] = {1: 0.30, 2: 0.38, 3: 0.50, 4: 0.58, 5: 0.65}.get(
            int(crop.drought_tolerance),
            0.50,
        )
    if crop.common_diseases:
        diseases = {
            str(item.get("id") or item.get("name") or "").lower()
            for item in crop.common_diseases
            if isinstance(item, dict)
        }
        if {"late_blight", "фітофтора", "фітофтороз"} & diseases:
            data["sus_late_blight"] = 0.75
        if {"powdery_mildew", "борошниста роса"} & diseases:
            data["sus_powdery_mildew"] = 0.70
        if {"downy_mildew", "мілдью"} & diseases:
            data["sus_downy_mildew"] = 0.70
        if {"botrytis", "сіра гниль"} & diseases:
            data["sus_botrytis"] = 0.65

    # Зберігаємо в plant_profiles для наступних звернень
    profile = await _save_profile(sanitize_profile_data(data, name, crop.category or "Овочі", "catalog"), db)

    return profile


async def create_profile_from_curated(name: str, category: str, db: AsyncSession):
    normalized = _normalize_name(name)
    data = _CURATED_PROFILES.get(normalized)
    if not data:
        return None
    profile_data = sanitize_profile_data(data, name, category, "curated")
    logger.info("Профіль '%s': створено з curated baseline '%s'", name, normalized)
    return await _save_profile(profile_data, db)


# ══════════════════════════════════════════════════════════════════════════════
# GEMINI AI INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-2.5-flash:generateContent"
)

_PROFILE_PROMPT = """Ти — агроном-експерт з 30-річним досвідом. Дай точні агрономічні
параметри для рослини "{plant_name}" (категорія: {category}).

Відповідай ТІЛЬКИ у форматі JSON, без пояснень, без ```json обгортки:

{{
  "name": "{plant_name}",
  "emoji": "🌱",
  "category": "{category}",
  "description": "Коротка характеристика рослини українською (1-2 речення)",
  "kc_initial": 0.40,
  "kc_mid": 1.05,
  "kc_end": 0.70,
  "initial_days": 20,
  "development_days": 30,
  "mid_season_days": 35,
  "late_season_days": 20,
  "root_depth_initial_cm": 10,
  "root_depth_max_cm": 50,
  "field_capacity_mm": 180,
  "wilting_point_mm": 55,
  "critical_depletion": 0.50,
  "t_min_growth": 8,
  "t_optimal_min": 18,
  "t_optimal_max": 28,
  "t_max_growth": 38,
  "frost_tolerance": 0,
  "nitrogen": 2.0,
  "phosphorus": 1.0,
  "potassium": 2.0,
  "magnesium": 0.3,
  "calcium": 0.5,
  "sus_late_blight": 0.3,
  "sus_powdery_mildew": 0.3,
  "sus_downy_mildew": 0.3,
  "sus_botrytis": 0.2,
  "days_to_harvest_min": 60,
  "days_to_harvest_max": 90,
  "disease_protection_adaptation_days": 5,
  "disease_protection_early_symptom_days": 2,
  "biofungicide_allowed_from_day": 0,
  "chemical_fungicide_allowed_from_day": 5,
  "copper_fungicide_allowed_from_day": 7,
  "max_spray_temp_c": 28,
  "avoid_spray_before_rain_hours": 6,
  "cold_stress_threshold_c": null,
  "frost_critical_threshold_c": 0
}}

ВАЖЛИВО:
- kc_initial/mid/end — коефіцієнти водоспоживання за FAO-56
- Дні стадій — реальні для цієї рослини
- Сума днів стадій має приблизно відповідати повному сезону культури
- root_depth_initial_cm <= root_depth_max_cm
- wilting_point_mm < field_capacity_mm
- t_min_growth < t_optimal_min <= t_optimal_max < t_max_growth
- Температури — мінімальна для росту, оптимальний діапазон, максимальна
- frost_tolerance — мінімальна температура яку витримає (напр. -5 для морозостійких)
- Вразливість до хвороб 0.0-1.0 (0=стійка, 1=дуже вразлива)
- Дні до врожаю — від висадки до першого збору
- Якщо не впевнений у точних даних, обери консервативне середнє значення, не екстремум
"""


_PROFILE_PROMPT += """

ДОДАТКОВІ ПРАВИЛА ДЛЯ ТОЧНОГО АГРОАНАЛІЗУ:
- disease_protection_adaptation_days — скільки днів після посадки/висадки рослину краще не навантажувати профілактичними хімічними фунгіцидами.
- disease_protection_early_symptom_days — з якого дня після посадки при явних симптомах можна обережно радити м'який захист.
- biofungicide_allowed_from_day — день після посадки, з якого дозволені біофунгіциди / мікробіологічні препарати; часто 0.
- chemical_fungicide_allowed_from_day — день після посадки, з якого допустимі звичайні хімічні фунгіциди для профілактики.
- copper_fungicide_allowed_from_day — день після посадки, з якого допустимі мідьвмісні препарати; для ніжної розсади зазвичай не раніше 5-7 днів.
- max_spray_temp_c — максимальна температура повітря для безпечного обприскування листя цієї культури; якщо не впевнений, став 25-28.
- avoid_spray_before_rain_hours — скільки годин до очікуваного дощу не варто обприскувати.
- cold_stress_threshold_c — температура мінімуму ночі, нижче якої потрібне попередження про холодовий стрес. Не плутай із t_min_growth: для морозостійких ягід/дерев/кущів це може бути 0 або нижче, а не +8/+10.
- frost_critical_threshold_c — температура, нижче якої є ризик реального пошкодження морозом у поточній культурі/фазі. Для теплолюбних овочів може бути 0..+2, для малини/смородини часто мінусова.
- Для томатів/перцю/огірків після висадки розсади: біозахист можна майже одразу, профілактичні хімічні фунгіциди краще через 5-7 днів, сильні/мідьвмісні — обережно після адаптації.
- Для багаторічних ягідних кущів і плодових культур не став cold_stress_threshold_c як t_min_growth; попереджай тільки про температуру, яка реально шкодить листю/квітам/зав'язі.
"""


async def ask_gemini(plant_name: str, category: str, user_id: object | None = None) -> dict | None:
    """
    Крок 4: генерація профілю через Gemini 2.5 Flash.
    Викликається лише коли всі локальні пошуки не дали результату.
    """
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY не встановлено — профіль не згенерується")
        return None
    if settings.GEMINI_DAILY_BUDGET <= 0:
        logger.warning("GEMINI_DAILY_BUDGET <= 0 — Gemini lookup disabled")
        return None

    budget_key = f"gemini:profile_lookup:{date.today().isoformat()}"
    try:
        redis = await get_cache_redis()
        used = await redis.incr(budget_key)
        if used == 1:
            await redis.expire(budget_key, 36 * 3600)
        if used > settings.GEMINI_DAILY_BUDGET:
            logger.warning(
                "Gemini daily budget exhausted: used=%s budget=%s",
                used,
                settings.GEMINI_DAILY_BUDGET,
            )
            return None
    except Exception as exc:
        logger.error("Gemini budget Redis check failed; skipping API call: %s", exc)
        return None

    prompt = _PROFILE_PROMPT.format(plant_name=plant_name, category=category)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            await record_gemini_usage("plant_profile", user_id)
            resp = await client.post(
                f"{_GEMINI_URL}?key={settings.GEMINI_API_KEY}",
                json=payload,
            )

        if resp.status_code != 200:
            logger.error("Gemini HTTP %d: %s", resp.status_code, resp.text[:300])
            return None

        data = resp.json()
        text_response = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Очищення markdown-огорток
        if text_response.startswith("```"):
            text_response = text_response.split("\n", 1)[1]
            text_response = text_response.rsplit("```", 1)[0]

        result = json.loads(text_response)
        logger.info(
            "Gemini профіль для '%s': Kc=%.2f, врожай %d-%d днів",
            plant_name,
            result.get("kc_mid", 0),
            result.get("days_to_harvest_min", 0),
            result.get("days_to_harvest_max", 0),
        )
        return result

    except Exception:
        logger.exception("Gemini API помилка для '%s'", plant_name)
        return None


async def create_profile_from_gemini(
    name: str, category: str, db: AsyncSession, user_id: object | None = None
):
    """Генерує профіль через Gemini та зберігає в БД."""
    from app.models.plant_profile import PlantProfile

    gemini_data = await ask_gemini(name, category, user_id=user_id)
    if not gemini_data:
        return None

    profile_data = sanitize_profile_data(gemini_data, name, category, "gemini")
    profile = await _save_profile(profile_data, db)
    if profile:
        logger.info("Профіль '%s' збережено в БД (джерело: gemini)", name)

    return profile


# ══════════════════════════════════════════════════════════════════════════════
# UNIFIED LOOKUP (головна точка входу)
# ══════════════════════════════════════════════════════════════════════════════

async def lookup_profile(
    name: str,
    category: str,
    db: AsyncSession,
    allow_gemini: bool = True,
    user_id: object | None = None,
) -> dict:
    """
    Єдина точка входу для пошуку профілю рослини.
    Повертає dict з FAO-56 параметрами (завжди — навіть якщо Gemini недоступний).

    Порядок пошуку:
      1. Точний збіг → plant_profiles
      2. Нечіткий (fuzzy) → plant_profiles (trigram similarity)
      3. crop_catalog → створення базового профілю
      4. Gemini AI → генерація повного FAO-56 профілю
      5. Defaults (якщо все failed)
    """
    name = name.strip()
    if not name:
        return _default_profile(name, category)

    # 1. Точний збіг
    profile = await find_profile_exact(name, db)
    if profile:
        logger.debug("Профіль '%s': точний збіг (source=%s)", name, profile.source)
        return profile.to_dict()

    # 2. Нечіткий пошук
    profile = await find_profile_fuzzy(name, db)
    if profile:
        logger.info("Профіль '%s': fuzzy match → '%s'", name, profile.name)
        return profile.to_dict()

    # 3. Каталог культур
    profile = await find_in_crop_catalog(name, db)
    if profile:
        logger.info("Профіль '%s': створено з crop_catalog", name)
        return profile.to_dict()

    # 4. Curated baseline для найчастіших культур — стабільніше за LLM.
    profile = await create_profile_from_curated(name, category, db)
    if profile:
        return profile.to_dict()

    # 5. Gemini AI
    if allow_gemini:
        profile = await create_profile_from_gemini(name, category, db, user_id=user_id)
        if profile:
            return profile.to_dict()
    else:
        logger.info("Профіль '%s': Gemini skipped by per-request budget", name)

    # 6. Defaults
    logger.warning("Профіль '%s': Gemini недоступний, використано defaults", name)
    return _default_profile(name, category)


def _default_profile(name: str, category: str) -> dict:
    """Профіль за замовчуванням коли всі джерела недоступні."""
    return sanitize_profile_data(None, name, category, "default")
