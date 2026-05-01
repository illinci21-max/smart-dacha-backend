"""Protection product primitives for disease-risk recommendations.

Profiles describe generic protection classes rather than branded pesticides.
They carry safety and resistance-management metadata that the agro engine can
use immediately: FRAC group, PHI, REI, rainfastness and spray-window limits.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProtectionProfile:
    id: str
    label: str
    protection_type: str
    target_diseases: list[str]
    frac_group: str
    mode_of_action: str
    reentry_days: int
    pre_harvest_interval_days: int
    rainfast_hours: int
    max_applications_per_season: int
    min_interval_days: int
    preventive: bool = True
    curative: bool = False
    max_wind_ms: float = 5.0
    max_temp_c: float = 28.0
    avoid_rain_next_hours: int = 6
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "protection_type": self.protection_type,
            "target_diseases": self.target_diseases,
            "frac_group": self.frac_group,
            "mode_of_action": self.mode_of_action,
            "reentry_days": self.reentry_days,
            "pre_harvest_interval_days": self.pre_harvest_interval_days,
            "rainfast_hours": self.rainfast_hours,
            "max_applications_per_season": self.max_applications_per_season,
            "min_interval_days": self.min_interval_days,
            "preventive": self.preventive,
            "curative": self.curative,
            "max_wind_ms": self.max_wind_ms,
            "max_temp_c": self.max_temp_c,
            "avoid_rain_next_hours": self.avoid_rain_next_hours,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ProtectionRecommendation:
    disease: str
    profile: ProtectionProfile
    explanation: str
    reasons: list[str]

    @property
    def recommendation_type(self) -> str:
        return self.profile.protection_type
