"""Fertilizer profile primitives for agro-analysis.

These profiles describe fertilizer classes, not commercial products. The engine
uses them to explain why it recommends mineral, organic, foliar, root-start, or
calcium-magnesium feeding under a given crop phase, soil and weather window.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FertilizerProfile:
    id: str
    label: str
    fertilizer_type: str
    application_method: str
    n_pct: float = 0.0
    p_pct: float = 0.0
    k_pct: float = 0.0
    mg_pct: float = 0.0
    ca_pct: float = 0.0
    organic_matter_pct: float = 0.0
    release_speed: str = "medium"
    leaching_risk: float = 0.4
    salt_index: float = 0.4
    suitable_goals: list[str] = field(default_factory=list)
    avoid_before_rain_mm: float = 10.0
    max_temp_c: float = 30.0
    max_wind_ms: float = 6.0
    requires_soil_moisture: bool = True

    @property
    def nutrient_label(self) -> str:
        parts = []
        if self.n_pct:
            parts.append(f"N {self.n_pct:g}%")
        if self.p_pct:
            parts.append(f"P {self.p_pct:g}%")
        if self.k_pct:
            parts.append(f"K {self.k_pct:g}%")
        if self.mg_pct:
            parts.append(f"Mg {self.mg_pct:g}%")
        if self.ca_pct:
            parts.append(f"Ca {self.ca_pct:g}%")
        return ", ".join(parts) or "\u0431\u0435\u0437 NPK"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "fertilizer_type": self.fertilizer_type,
            "application_method": self.application_method,
            "n_pct": self.n_pct,
            "p_pct": self.p_pct,
            "k_pct": self.k_pct,
            "mg_pct": self.mg_pct,
            "ca_pct": self.ca_pct,
            "organic_matter_pct": self.organic_matter_pct,
            "release_speed": self.release_speed,
            "leaching_risk": self.leaching_risk,
            "salt_index": self.salt_index,
            "suitable_goals": self.suitable_goals,
            "avoid_before_rain_mm": self.avoid_before_rain_mm,
            "max_temp_c": self.max_temp_c,
            "max_wind_ms": self.max_wind_ms,
            "requires_soil_moisture": self.requires_soil_moisture,
            "nutrient_label": self.nutrient_label,
        }


@dataclass(frozen=True)
class FertilizerRecommendation:
    goal: str
    profile: FertilizerProfile
    amount: str
    explanation: str
    reasons: list[str]

    @property
    def recommendation_type(self) -> str:
        return self.profile.fertilizer_type
