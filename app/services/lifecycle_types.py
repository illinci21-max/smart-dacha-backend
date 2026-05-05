"""Lifecycle types for crop classification.

Distinguishes annual vegetables from perennial trees, shrubs, and herbaceous
perennials. Phenology models differ fundamentally between these groups.
"""
from __future__ import annotations

from enum import Enum


class LifecycleType(str, Enum):
    """How a plant lives across years."""

    ANNUAL = "annual"
    """Single growing season: tomato, cucumber, lettuce, basil."""

    BIENNIAL = "biennial"
    """Two-year cycle. Treated as annual until full biennial logic exists."""

    PERENNIAL_HERBACEOUS = "perennial_herbaceous"
    """Multi-year, dies back each winter: strawberry, asparagus, rhubarb."""

    PERENNIAL_WOODY_DECIDUOUS = "perennial_woody_deciduous"
    """Multi-year, woody, drops leaves: apple, pear, cherry, currant."""

    PERENNIAL_WOODY_EVERGREEN = "perennial_woody_evergreen"
    """Multi-year, woody, retains leaves: pine, spruce, evergreen herbs."""

    @property
    def is_perennial(self) -> bool:
        return self in {
            LifecycleType.PERENNIAL_HERBACEOUS,
            LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
            LifecycleType.PERENNIAL_WOODY_EVERGREEN,
        }

    @property
    def is_woody(self) -> bool:
        return self in {
            LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
            LifecycleType.PERENNIAL_WOODY_EVERGREEN,
        }

    @property
    def has_dormancy(self) -> bool:
        return self.is_perennial


class PerennialSeason(str, Enum):
    """Coarse seasonal phase for perennial plants.

    Used until full BBCH-stage modeling is implemented.
    Calendar-driven mapping for Northern Hemisphere temperate climate.
    """

    DORMANT_WINTER = "dormant_winter"
    BUD_BREAK = "bud_break"
    FLOWERING_FRUIT_SET = "flowering_fruit_set"
    FRUIT_DEVELOPMENT = "fruit_development"
    HARVEST_RIPENING = "harvest_ripening"
    LEAF_FALL = "leaf_fall"
    DORMANT_ENTRY = "dormant_entry"
