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
