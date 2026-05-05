"""Coarse seasonal phenology for perennial plants.

This is a simplified model used until full BBCH-scale phenology is implemented.
It maps calendar months to coarse seasonal phases for Northern Hemisphere
temperate climate, including Ukraine around 50 degrees north.
"""
from __future__ import annotations

from datetime import date

from app.services.lifecycle_types import LifecycleType, PerennialSeason


_NORTHERN_HEMISPHERE_SEASON_MAP: dict[int, PerennialSeason] = {
    1: PerennialSeason.DORMANT_WINTER,
    2: PerennialSeason.DORMANT_WINTER,
    3: PerennialSeason.BUD_BREAK,
    4: PerennialSeason.BUD_BREAK,
    5: PerennialSeason.FLOWERING_FRUIT_SET,
    6: PerennialSeason.FLOWERING_FRUIT_SET,
    7: PerennialSeason.FRUIT_DEVELOPMENT,
    8: PerennialSeason.HARVEST_RIPENING,
    9: PerennialSeason.HARVEST_RIPENING,
    10: PerennialSeason.LEAF_FALL,
    11: PerennialSeason.LEAF_FALL,
    12: PerennialSeason.DORMANT_ENTRY,
}


def determine_perennial_season(
    today: date,
    lifecycle: LifecycleType,
    *,
    is_productive: bool = True,
) -> PerennialSeason:
    """Determine coarse seasonal phase for a perennial plant."""
    if not lifecycle.is_perennial:
        raise ValueError(
            f"determine_perennial_season called for non-perennial: {lifecycle}"
        )

    base = _NORTHERN_HEMISPHERE_SEASON_MAP[today.month]

    if today.month == 6 and today.day >= 16:
        base = PerennialSeason.FRUIT_DEVELOPMENT

    if not is_productive and base in (
        PerennialSeason.FLOWERING_FRUIT_SET,
        PerennialSeason.FRUIT_DEVELOPMENT,
        PerennialSeason.HARVEST_RIPENING,
    ):
        return PerennialSeason.FRUIT_DEVELOPMENT

    return base


DEFAULT_PRODUCTIVE_AGE_YEARS: dict[LifecycleType, int] = {
    LifecycleType.PERENNIAL_HERBACEOUS: 1,
    LifecycleType.PERENNIAL_WOODY_DECIDUOUS: 4,
    LifecycleType.PERENNIAL_WOODY_EVERGREEN: 5,
}


def is_plant_productive(
    age_years: int | None,
    lifecycle: LifecycleType,
    productive_age_override: int | None = None,
) -> bool:
    """Check if a perennial plant has reached productive age."""
    if age_years is None:
        return True
    threshold = productive_age_override or DEFAULT_PRODUCTIVE_AGE_YEARS.get(
        lifecycle, 4
    )
    return age_years >= threshold


# Coarse fertilizer/protection needs by perennial season.
# Quantities are per square meter of crown area until cultivar BBCH data exists.
PERENNIAL_FERTILIZER_BY_SEASON: dict[PerennialSeason, dict[str, float]] = {
    PerennialSeason.DORMANT_WINTER: {},
    PerennialSeason.BUD_BREAK: {
        "nitrogen": 6.0,
        "phosphorus": 3.0,
        "potassium": 3.0,
        "boron": 0.04,
        "zinc": 0.03,
    },
    PerennialSeason.FLOWERING_FRUIT_SET: {
        "nitrogen": 2.0,
        "phosphorus": 4.0,
        "potassium": 4.0,
        "boron": 0.06,
        "zinc": 0.04,
        "calcium": 2.0,
    },
    PerennialSeason.FRUIT_DEVELOPMENT: {
        "nitrogen": 3.0,
        "phosphorus": 2.0,
        "potassium": 8.0,
        "calcium": 2.5,
        "magnesium": 0.8,
    },
    PerennialSeason.HARVEST_RIPENING: {
        "nitrogen": 0.0,
        "phosphorus": 1.0,
        "potassium": 5.0,
    },
    PerennialSeason.LEAF_FALL: {
        "phosphorus": 4.0,
        "potassium": 3.0,
    },
    PerennialSeason.DORMANT_ENTRY: {},
}


PERENNIAL_DISEASE_PRESSURE: dict[PerennialSeason, dict[str, float]] = {
    PerennialSeason.DORMANT_WINTER: {},
    PerennialSeason.BUD_BREAK: {
        "apple_scab": 0.6,
        "powdery_mildew": 0.3,
    },
    PerennialSeason.FLOWERING_FRUIT_SET: {
        "apple_scab": 0.85,
        "fire_blight": 0.7,
        "monilinia": 0.6,
    },
    PerennialSeason.FRUIT_DEVELOPMENT: {
        "apple_scab": 0.5,
        "powdery_mildew": 0.5,
        "alternaria": 0.4,
    },
    PerennialSeason.HARVEST_RIPENING: {
        "monilinia": 0.7,
        "alternaria": 0.5,
    },
    PerennialSeason.LEAF_FALL: {
        "apple_scab": 0.4,
    },
    PerennialSeason.DORMANT_ENTRY: {},
}


PERENNIAL_FROST_SENSITIVITY: dict[PerennialSeason, float] = {
    PerennialSeason.DORMANT_WINTER: 0.05,
    PerennialSeason.BUD_BREAK: 0.40,
    PerennialSeason.FLOWERING_FRUIT_SET: 0.95,
    PerennialSeason.FRUIT_DEVELOPMENT: 0.30,
    PerennialSeason.HARVEST_RIPENING: 0.20,
    PerennialSeason.LEAF_FALL: 0.10,
    PerennialSeason.DORMANT_ENTRY: 0.05,
}


def get_perennial_fertilizer_need(season: PerennialSeason) -> dict[str, float]:
    """Return seasonal fertilizer needs in g/m2 of crown area."""
    return PERENNIAL_FERTILIZER_BY_SEASON.get(season, {}).copy()


def get_perennial_disease_pressure(season: PerennialSeason) -> dict[str, float]:
    """Return coarse disease pressure hints for the season."""
    return PERENNIAL_DISEASE_PRESSURE.get(season, {}).copy()


def get_perennial_frost_sensitivity(season: PerennialSeason) -> float:
    """Return frost sensitivity from 0 to 1 for the season."""
    return PERENNIAL_FROST_SENSITIVITY.get(season, 0.0)
