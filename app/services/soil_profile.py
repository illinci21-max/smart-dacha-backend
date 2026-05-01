"""Soil profile primitives for agro analysis.

A soil profile describes field properties that belong to the plot, not to the
crop. PlantProfile defines crop biology; SoilProfile defines water holding,
drainage, nutrient retention, aeration, pH and disease-pressure modifiers.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SoilProfile:
    id: str
    label: str
    field_capacity_mm_per_m: float
    wilting_point_mm_per_m: float
    ph_min: float = 6.0
    ph_max: float = 7.2
    organic_matter_pct: float = 3.0
    bulk_density_g_cm3: float = 1.35
    drainage_class: str = "moderate"
    effective_rain_multiplier: float = 1.0
    drainage_multiplier: float = 1.0
    disease_risk_multiplier: float = 1.0
    compaction_risk: float = 0.3
    infiltration_rate_mm_h: float = 12.0
    nutrient_retention: float = 0.55
    nitrogen_leaching_multiplier: float = 1.0
    phosphorus_fixation_risk: float = 0.25
    potassium_retention: float = 0.55
    salinity_risk: float = 0.2
    waterlogging_risk: float = 0.25
    aeration_risk: float = 0.25
    initial_n_g_m2: float = 4.0
    initial_p_g_m2: float = 3.0
    initial_k_g_m2: float = 5.0
    initial_mg_g_m2: float = 1.5
    initial_ca_g_m2: float = 12.0

    @property
    def available_water_mm_per_m(self) -> float:
        return max(10.0, self.field_capacity_mm_per_m - self.wilting_point_mm_per_m)

    @property
    def ph_label(self) -> str:
        return f"{self.ph_min:.1f}-{self.ph_max:.1f}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "field_capacity_mm_per_m": self.field_capacity_mm_per_m,
            "wilting_point_mm_per_m": self.wilting_point_mm_per_m,
            "available_water_mm_per_m": self.available_water_mm_per_m,
            "ph_min": self.ph_min,
            "ph_max": self.ph_max,
            "ph_label": self.ph_label,
            "organic_matter_pct": self.organic_matter_pct,
            "bulk_density_g_cm3": self.bulk_density_g_cm3,
            "drainage_class": self.drainage_class,
            "effective_rain_multiplier": self.effective_rain_multiplier,
            "drainage_multiplier": self.drainage_multiplier,
            "disease_risk_multiplier": self.disease_risk_multiplier,
            "compaction_risk": self.compaction_risk,
            "infiltration_rate_mm_h": self.infiltration_rate_mm_h,
            "nutrient_retention": self.nutrient_retention,
            "nitrogen_leaching_multiplier": self.nitrogen_leaching_multiplier,
            "phosphorus_fixation_risk": self.phosphorus_fixation_risk,
            "potassium_retention": self.potassium_retention,
            "salinity_risk": self.salinity_risk,
            "waterlogging_risk": self.waterlogging_risk,
            "aeration_risk": self.aeration_risk,
            "initial_n_g_m2": self.initial_n_g_m2,
            "initial_p_g_m2": self.initial_p_g_m2,
            "initial_k_g_m2": self.initial_k_g_m2,
            "initial_mg_g_m2": self.initial_mg_g_m2,
            "initial_ca_g_m2": self.initial_ca_g_m2,
        }


DEFAULT_SOIL_PROFILE = SoilProfile(
    id="loam",
    label="\u0421\u0443\u0433\u043b\u0438\u043d\u043e\u043a",
    field_capacity_mm_per_m=290,
    wilting_point_mm_per_m=140,
    ph_min=6.2,
    ph_max=7.3,
    organic_matter_pct=3.5,
    bulk_density_g_cm3=1.35,
    drainage_class="moderate",
    effective_rain_multiplier=1.0,
    drainage_multiplier=1.0,
    disease_risk_multiplier=1.0,
    compaction_risk=0.35,
    infiltration_rate_mm_h=12.0,
    nutrient_retention=0.60,
    nitrogen_leaching_multiplier=1.0,
    phosphorus_fixation_risk=0.25,
    potassium_retention=0.60,
    salinity_risk=0.20,
    waterlogging_risk=0.25,
    aeration_risk=0.25,
    initial_n_g_m2=6.0,
    initial_p_g_m2=4.5,
    initial_k_g_m2=7.0,
    initial_mg_g_m2=2.2,
    initial_ca_g_m2=16.0,
)
