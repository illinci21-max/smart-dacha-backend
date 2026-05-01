"""
Biodynamic Calendar Router — Maria Thun methodology.

Endpoint:
  GET /api/v1/biodynamic/forecast?days=10

Calculates:
  - Moon position in sidereal (astronomical) constellations
  - Element classification: Root/Leaf/Flower/Fruit
  - "Black days": lunar nodes, apogee/perigee, eclipses
  - Moon phase & illumination
  - Season-aware daily gardening recommendations in Ukrainian

Monetization:
  - Free users: only today (index=0), rest is locked
  - Pro users: full 10-day forecast
"""
import math
import logging
from datetime import date, timedelta, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from app.dependencies import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/biodynamic", tags=["biodynamic"])

# ══════════════════════════════════════════════════════════════════════════════
# ASTRONOMICAL ENGINE (ephem-based, sidereal zodiac)
# ══════════════════════════════════════════════════════════════════════════════

try:
    import ephem
except ImportError:
    ephem = None
    logger.warning("ephem not installed: pip install ephem")

# Lahiri ayanamsa for tropical → sidereal conversion
_AYANAMSA_J2000 = 23.856
_AYANAMSA_RATE = 0.01396  # deg/year


def _get_ayanamsa(year: int) -> float:
    return _AYANAMSA_J2000 + _AYANAMSA_RATE * (year - 2000)


# ── Sidereal constellations (Maria Thun: astronomical, unequal spans) ────────

_CONSTELLATIONS = [
    (0,   "Aries",       "♈", "Овен"),
    (30,  "Taurus",      "♉", "Телець"),
    (60,  "Gemini",      "♊", "Близнюки"),
    (90,  "Cancer",      "♋", "Рак"),
    (120, "Leo",         "♌", "Лев"),
    (150, "Virgo",       "♍", "Діва"),
    (180, "Libra",       "♎", "Терези"),
    (210, "Scorpio",     "♏", "Скорпіон"),
    (240, "Sagittarius", "♐", "Стрілець"),
    (270, "Capricorn",   "♑", "Козеріг"),
    (300, "Aquarius",    "♒", "Водолій"),
    (330, "Pisces",      "♓", "Риби"),
]

# Maria Thun element classification
_ELEMENT_MAP = {
    # Root (Earth) — Taurus, Virgo, Capricorn
    "Taurus": "root", "Virgo": "root", "Capricorn": "root",
    # Leaf (Water) — Cancer, Scorpio, Pisces
    "Cancer": "leaf", "Scorpio": "leaf", "Pisces": "leaf",
    # Flower (Air) — Gemini, Libra, Aquarius
    "Gemini": "flower", "Libra": "flower", "Aquarius": "flower",
    # Fruit (Fire) — Aries, Leo, Sagittarius
    "Aries": "fruit", "Leo": "fruit", "Sagittarius": "fruit",
}

# ══════════════════════════════════════════════════════════════════════════════
# SEASON-AWARE RECOMMENDATIONS (Ukrainian agricultural practice)
# ══════════════════════════════════════════════════════════════════════════════

def _get_season(d: date) -> str:
    """Determine agricultural season for Ukraine (temperate continental)."""
    month = d.month
    if month in (3, 4, 5):
        return "spring"
    elif month in (6, 7, 8):
        return "summer"
    elif month in (9, 10, 11):
        return "autumn"
    else:
        return "winter"


# ── Element info (static parts) ──────────────────────────────────────────────

_ELEMENT_BASE = {
    "root": {
        "name_uk": "Корінь",
        "element": "Земля",
        "color": "#8B6914",
        "icon": "🥕",
        "emoji": "🌍",
    },
    "leaf": {
        "name_uk": "Лист",
        "element": "Вода",
        "color": "#1E90FF",
        "icon": "🥬",
        "emoji": "💧",
    },
    "flower": {
        "name_uk": "Квітка",
        "element": "Повітря",
        "color": "#FF69B4",
        "icon": "🌸",
        "emoji": "💨",
    },
    "fruit": {
        "name_uk": "Плід",
        "element": "Вогонь",
        "color": "#FF6347",
        "icon": "🍅",
        "emoji": "🔥",
    },
}

# ── Season-dependent works ───────────────────────────────────────────────────

_SEASON_WORKS = {
    # ═══ ROOT (Earth) ═══
    "root": {
        "spring": {
            "works": [
                "Посів коренеплодів (морква, буряк, редис, пастернак)",
                "Садіння картоплі та цибулі-сіянки",
                "Розпушування та підготовка ґрунту",
                "Внесення компосту та перегною в грядки",
            ],
            "avoid": [
                "Обрізка плодових дерев (пізно навесні)",
                "Пересадка рослин з відкритим корінням",
            ],
        },
        "summer": {
            "works": [
                "Підгортання картоплі та коренеплодів",
                "Прополювання міжрядь коренеплодів",
                "Проріджування моркви, буряка",
                "Збирання раннього редису та молодої картоплі",
            ],
            "avoid": [
                "Посів коренеплодів (пізно для довгосезонних)",
                "Глибоке перекопування поруч з рослинами",
            ],
        },
        "autumn": {
            "works": [
                "Збирання картоплі, моркви, буряка на зберігання",
                "Садіння озимої цибулі та часнику",
                "Закладання коренеплодів у підвал",
                "Підготовка ґрунту під зиму (перекопування з гноєм)",
            ],
            "avoid": [
                "Полив коренеплодів перед збиранням",
                "Садіння теплолюбних культур",
            ],
        },
        "winter": {
            "works": [
                "Перевірка умов зберігання коренеплодів",
                "Планування грядок під коренеплоди на наступний рік",
                "Замовлення насіння моркви, буряка, картоплі",
                "Закупівля мінеральних добрив",
            ],
            "avoid": [
                "Будь-які польові роботи (ґрунт замерзлий)",
                "Посів у непрогрітий ґрунт",
            ],
        },
    },

    # ═══ LEAF (Water) ═══
    "leaf": {
        "spring": {
            "works": [
                "Посів листових овочів (салат, шпинат, руккола, укроп)",
                "Висадка розсади капусти (білокачанна, броколі, кольрабі)",
                "Полив та підгодівля рідкими добривами",
                "Мульчування грядок для збереження вологи",
            ],
            "avoid": [
                "Обрізка виноградної лози (соковитий рух)",
                "Збирання трав на сушіння (занадто вологі)",
            ],
        },
        "summer": {
            "works": [
                "Полив усіх культур (оптимальний день для поливу!)",
                "Збирання листової зелені для свіжого вживання",
                "Стрижка газону та формування живоплоту",
                "Повторний посів салату та укропу",
            ],
            "avoid": [
                "Збирання овочів та фруктів для зберігання (надто соковиті)",
                "Консервування та сушіння (погано зберігатиметься)",
            ],
        },
        "autumn": {
            "works": [
                "Збирання пізньої капусти та листової зелені",
                "Полив озимих посівів та саджанців",
                "Квашення капусти (ідеальний день!)",
                "Підгодівля рідкими органічними добривами",
            ],
            "avoid": [
                "Закладання коренеплодів на зберігання (гниття)",
                "Обрізка дерев (рани мокнуть)",
            ],
        },
        "winter": {
            "works": [
                "Полив кімнатних рослин та розсади на підвіконні",
                "Вигонка цибулі на зелень у воді",
                "Замочування насіння перед посівом на розсаду",
                "Перевірка вологості у сховищі овочів",
            ],
            "avoid": [
                "Сушіння трав та спецій",
                "Збирання врожаю з теплиць на зберігання",
            ],
        },
    },

    # ═══ FLOWER (Air) ═══
    "flower": {
        "spring": {
            "works": [
                "Посадка та пересадка квіткових культур",
                "Вивільнення троянд та клематисів з укриттів",
                "Посів однорічних квітів (бархатці, петунії, цинії)",
                "Ділення та розсадження багаторічників",
            ],
            "avoid": [
                "Рясний полив (краще у Лист-дні)",
                "Посів коренеплодів",
            ],
        },
        "summer": {
            "works": [
                "Збирання лікарських трав та квітів для сушіння",
                "Зрізання квітів для букетів (довго стоятимуть)",
                "Обрізка відцвілих суцвіть для повторного цвітіння",
                "Підживлення квітучих рослин фосфорно-калійними добривами",
            ],
            "avoid": [
                "Надмірний полив квітів",
                "Садіння нових рослин у спеку",
            ],
        },
        "autumn": {
            "works": [
                "Викопування бульб жоржин, гладіолусів, канн",
                "Садіння тюльпанів, нарцисів, крокусів (озимі цибулини)",
                "Збирання насіння квітів для наступного сезону",
                "Укриття троянд та теплолюбних багаторічників",
            ],
            "avoid": [
                "Полив рослин перед заморозками",
                "Пересадка рослин у холодний ґрунт",
            ],
        },
        "winter": {
            "works": [
                "Замовлення насіння та цибулин квітів на весну",
                "Догляд за кімнатними квітучими рослинами",
                "Планування квітників та клумб",
                "Стратифікація насіння багаторічників",
            ],
            "avoid": [
                "Пересадка кімнатних рослин (зимовий спокій)",
                "Активна підгодівля кімнатних квітів",
            ],
        },
    },

    # ═══ FRUIT (Fire) ═══
    # «Плід» за Марією Тун = день для рослин, що формують плоди
    # (томат, перець, огірок, кабачок, баклажан, гарбуз, горох, квасоля)
    "fruit": {
        "spring": {
            "works": [
                "Висадка розсади томатів, перців, баклажанів у теплицю",
                "Посів огірків, кабачків, гарбузів на розсаду",
                "Посів гороху, квасолі, кукурудзи у відкритий ґрунт",
                "Прищипування розсади для кращого розгалуження",
            ],
            "avoid": [
                "Полив розсади (підвищує ризик чорної ніжки)",
                "Внесення свіжого гною під плодоносні культури",
            ],
        },
        "summer": {
            "works": [
                "Пасинкування та підв'язування томатів",
                "Збирання стиглих томатів, огірків, перців, кабачків",
                "Формування кущів огірків та гарбузів",
                "Підживлення плодоносних рослин калійними добривами",
            ],
            "avoid": [
                "Рясний полив (плоди розтріскуються, гниють)",
                "Внесення азотних добрив (йде в зелень, не в плоди)",
            ],
        },
        "autumn": {
            "works": [
                "Збирання пізніх томатів, перців, баклажанів",
                "Дозрівання зелених томатів у приміщенні",
                "Збирання гарбузів та кабачків на зберігання",
                "Збирання насіння з найкращих плодів на наступний рік",
            ],
            "avoid": [
                "Полив плодоносних рослин перед збиранням",
                "Залишання плодів на грядці при загрозі заморозків",
            ],
        },
        "winter": {
            "works": [
                "Перевірка схожості насіння томатів, перців",
                "Замовлення нових сортів на наступний сезон",
                "Планування сівозміни для плодоносних культур",
                "Ранній посів перців та баклажанів на розсаду (лютий)",
            ],
            "avoid": [
                "Ранній посів без додаткового освітлення",
                "Перегрівання розсади на підвіконні",
            ],
        },
    },
}


def _get_element_info(element: str, season: str) -> dict:
    """Get combined element info with season-specific recommendations."""
    base = _ELEMENT_BASE[element]
    season_data = _SEASON_WORKS[element].get(season, _SEASON_WORKS[element]["spring"])
    return {
        **base,
        "works_uk": season_data["works"],
        "avoid_uk": season_data["avoid"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# CONSTELLATION & PHASE CALCULATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _get_constellation(tropical_lon_deg: float, year: int):
    """Convert tropical ecliptic longitude to sidereal constellation."""
    ayanamsa = _get_ayanamsa(year)
    sidereal = (tropical_lon_deg - ayanamsa) % 360
    for i in range(len(_CONSTELLATIONS) - 1, -1, -1):
        if sidereal >= _CONSTELLATIONS[i][0]:
            return _CONSTELLATIONS[i], sidereal
    return _CONSTELLATIONS[0], sidereal


def _moon_phase_name(phase_pct: float, is_waxing: bool) -> tuple[str, str]:
    if phase_pct < 3:
        return "new_moon", "🌑 Новий Місяць"
    elif phase_pct < 48:
        return ("waxing_crescent", "🌒 Молодий Місяць") if is_waxing \
            else ("waning_crescent", "🌘 Старий Місяць")
    elif phase_pct < 52:
        return ("first_quarter", "🌓 Перша чверть") if is_waxing \
            else ("last_quarter", "🌗 Остання чверть")
    elif phase_pct < 97:
        return ("waxing_gibbous", "🌔 Зростаючий Місяць") if is_waxing \
            else ("waning_gibbous", "🌖 Спадний Місяць")
    else:
        return "full_moon", "🌕 Повний Місяць"


def _daily_tip(element: str, is_waxing: bool, season: str) -> str:
    """Season-aware contextual tip."""
    phase = "Зростаючий Місяць — енергія піднімається вгору, соки рухаються до листя" \
        if is_waxing \
        else "Спадний Місяць — енергія опускається, соки рухаються до коренів"

    season_tips = {
        "spring": {
            "root": f"{phase}. Підготуйте грядки під коренеплоди.",
            "leaf": f"{phase}. Час сіяти зелень та листові овочі.",
            "flower": f"{phase}. Висаджуйте квіти та багаторічники.",
            "fruit": f"{phase}. Готуйте розсаду плодоносних овочів.",
        },
        "summer": {
            "root": f"{phase}. Підгортайте картоплю, проріджуйте коренеплоди.",
            "leaf": f"{phase}. Ідеальний день для поливу!",
            "flower": f"{phase}. Збирайте лікарські трави на сушіння.",
            "fruit": f"{phase}. Збирайте стиглі овочі, пасинкуйте томати.",
        },
        "autumn": {
            "root": f"{phase}. Збирайте коренеплоди на зимове зберігання.",
            "leaf": f"{phase}. Збирайте пізню капусту, квасіть на зиму.",
            "flower": f"{phase}. Садіть озимі цибулини (тюльпани, нарциси).",
            "fruit": f"{phase}. Збирайте останній врожай перед холодами.",
        },
        "winter": {
            "root": f"{phase}. Перевірте сховище овочів.",
            "leaf": f"{phase}. Поливайте кімнатні рослини.",
            "flower": f"{phase}. Плануйте весняні клумби.",
            "fruit": f"{phase}. Перевірте схожість насіння на розсаду.",
        },
    }
    return season_tips.get(season, season_tips["spring"]).get(element, phase)


def _day_name_uk(d: date) -> str:
    names = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
    return names[d.weekday()]


# ══════════════════════════════════════════════════════════════════════════════
# CALCULATE SINGLE DAY
# ══════════════════════════════════════════════════════════════════════════════

def _calculate_day(target_date: date) -> dict:
    if ephem is None:
        return _fallback_day(target_date)

    obs = ephem.Observer()
    obs.date = target_date.strftime("%Y/%m/%d 12:00:00")

    moon = ephem.Moon()
    moon.compute(obs)

    tropical_lon = math.degrees(float(moon.hlong))
    constellation, sidereal_lon = _get_constellation(tropical_lon, target_date.year)
    const_name_en = constellation[1]
    const_symbol = constellation[2]
    const_name_uk = constellation[3]

    element = _ELEMENT_MAP[const_name_en]
    season = _get_season(target_date)

    phase_pct = moon.phase

    # Waxing/waning
    obs2 = ephem.Observer()
    obs2.date = (target_date + timedelta(days=1)).strftime("%Y/%m/%d 12:00:00")
    moon2 = ephem.Moon()
    moon2.compute(obs2)
    is_waxing = moon2.phase > moon.phase or (moon.phase < 5 and moon2.phase > moon.phase)

    phase_en, phase_uk = _moon_phase_name(phase_pct, is_waxing)

    # ── "Black days" detection ───────────────────────────────────────────
    is_black_day = False
    black_reason = None

    lat_deg = math.degrees(float(moon.hlat))
    if abs(lat_deg) < 0.5:
        is_black_day = True
        black_reason = "Місячний вузол — уникайте садіння та збирання"

    distance_km = moon.earth_distance * 149597870.7
    if distance_km < 360000:
        is_black_day = True
        black_reason = "Перигей Місяця — рослини уразливі, уникайте робіт"
    elif distance_km > 405000:
        is_black_day = True
        black_reason = "Апогей Місяця — низька енергія, відпочиньте від городу"

    if abs(lat_deg) < 0.3 and (phase_pct < 3 or phase_pct > 97):
        is_black_day = True
        black_reason = "Затемнення — категорично уникайте будь-яких робіт з рослинами"

    # Build response with season-aware recommendations
    info = _get_element_info(element, season)

    return {
        "date": target_date.isoformat(),
        "day_of_week": _day_name_uk(target_date),
        "constellation_en": const_name_en,
        "constellation_uk": const_name_uk,
        "constellation_symbol": const_symbol,
        "sidereal_longitude": round(sidereal_lon, 1),
        "element": element,
        "element_name_uk": info["name_uk"],
        "element_emoji": info["emoji"],
        "element_color": info["color"],
        "icon": info["icon"],
        "moon_phase": phase_en,
        "moon_phase_uk": phase_uk,
        "moon_illumination": round(phase_pct, 1),
        "is_waxing": is_waxing,
        "is_black_day": is_black_day,
        "black_reason": black_reason,
        "season": season,
        "recommended_works": [] if is_black_day else info["works_uk"],
        "avoid_works": info["avoid_uk"] if not is_black_day else ["Усі роботи з рослинами — несприятливий день"],
        "tip": black_reason or _daily_tip(element, is_waxing, season),
        "is_locked": False,
    }


def _fallback_day(target_date: date) -> dict:
    """Fallback when ephem is not available."""
    day_num = (target_date - date(2000, 1, 6)).days
    cycle_pos = (day_num % 27.3) / 27.3
    const_idx = int(cycle_pos * 12) % 12
    constellation = _CONSTELLATIONS[const_idx]
    element = _ELEMENT_MAP[constellation[1]]
    season = _get_season(target_date)
    info = _get_element_info(element, season)

    return {
        "date": target_date.isoformat(),
        "day_of_week": _day_name_uk(target_date),
        "constellation_en": constellation[1],
        "constellation_uk": constellation[3],
        "constellation_symbol": constellation[2],
        "sidereal_longitude": round(const_idx * 30 + 15, 1),
        "element": element,
        "element_name_uk": info["name_uk"],
        "element_emoji": info["emoji"],
        "element_color": info["color"],
        "icon": info["icon"],
        "moon_phase": "unknown",
        "moon_phase_uk": "🌙 Розраховується...",
        "moon_illumination": 50.0,
        "is_waxing": True,
        "is_black_day": False,
        "black_reason": None,
        "season": season,
        "recommended_works": info["works_uk"],
        "avoid_works": info["avoid_uk"],
        "tip": "Встановіть бібліотеку ephem для точних астрономічних розрахунків",
        "is_locked": False,
    }


def _locked_day(target_date: date) -> dict:
    return {
        "date": target_date.isoformat(),
        "day_of_week": _day_name_uk(target_date),
        "is_locked": True,
        "element": None,
        "element_name_uk": "🔒",
        "element_color": "#9CA3AF",
        "icon": "🔒",
        "constellation_uk": "—",
        "moon_phase_uk": "—",
        "tip": "Доступно для PRO підписки",
    }


# ══════════════════════════════════════════════════════════════════════════════
# ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/forecast")
async def get_biodynamic_forecast(
    days: int = Query(10, ge=1, le=30),
    current_user: User = Depends(get_current_user),
):
    """
    Get biodynamic calendar forecast.

    Free users: only today is unlocked.
    Pro users: full forecast for `days` days.
    """
    is_pro = current_user.subscription_tier in ("premium", "premium_plus")
    today = date.today()

    forecast = []
    for i in range(days):
        target = today + timedelta(days=i)

        if i == 0 or is_pro:
            day_data = _calculate_day(target)
        else:
            day_data = _locked_day(target)

        day_data["index"] = i
        day_data["is_today"] = (i == 0)
        forecast.append(day_data)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "is_pro": is_pro,
        "days": forecast,
    }