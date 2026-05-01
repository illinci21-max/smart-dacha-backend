"""Curated soil profile catalog used by the agro-analysis engine."""
from __future__ import annotations

from dataclasses import fields

from app.services.soil_profile import DEFAULT_SOIL_PROFILE, SoilProfile


PH_FROM_SURVEY: dict[str, tuple[float, float] | None] = {
    "acidic": (4.8, 5.5),
    "slightly_acidic": (5.5, 6.3),
    "neutral": (6.3, 7.0),
    "slightly_alkaline": (7.0, 7.6),
    "alkaline": (7.6, 8.4),
    "unknown": None,
}

DRAINAGE_FROM_SURVEY: dict[str, dict[str, float] | None] = {
    "fast": {"effective_rain_multiplier": 0.55, "waterlogging_risk": 0.05},
    "good": {"effective_rain_multiplier": 0.85, "waterlogging_risk": 0.15},
    "moderate": None,
    "slow": {"effective_rain_multiplier": 1.05, "waterlogging_risk": 0.45},
    "waterlogged": {"effective_rain_multiplier": 1.15, "waterlogging_risk": 0.75},
}

ORGANIC_INPUT_FROM_SURVEY: dict[str, dict[str, float] | None] = {
    "none": {"om_multiplier": 0.85, "n_boost_g_m2": 0.0, "p_boost_g_m2": 0.0, "k_boost_g_m2": 0.0},
    "thin": {"om_multiplier": 1.00, "n_boost_g_m2": 1.0, "p_boost_g_m2": 0.5, "k_boost_g_m2": 1.0},
    "regular": {"om_multiplier": 1.30, "n_boost_g_m2": 4.0, "p_boost_g_m2": 2.0, "k_boost_g_m2": 4.0},
    "heavy": {"om_multiplier": 1.60, "n_boost_g_m2": 8.0, "p_boost_g_m2": 4.0, "k_boost_g_m2": 8.0},
    "unknown": None,
}


class PlotOverrides:
    def __init__(
        self,
        ph_class: str | None = None,
        drainage_class: str | None = None,
        organic_input: str | None = None,
        last_season_quality: str | None = None,
    ):
        self.ph_class = ph_class
        self.drainage_class = drainage_class
        self.organic_input = organic_input
        self.last_season_quality = last_season_quality

    @classmethod
    def from_plot(cls, plot) -> "PlotOverrides":
        return cls(
            ph_class=getattr(plot, "plot_ph_class", None),
            drainage_class=getattr(plot, "plot_drainage_class", None),
            organic_input=getattr(plot, "plot_organic_input", None),
            last_season_quality=getattr(plot, "plot_last_season_quality", None),
        )

    def apply_to(self, soil: SoilProfile) -> SoilProfile:
        values = {field.name: getattr(soil, field.name) for field in fields(soil)}

        ph_range = PH_FROM_SURVEY.get(self.ph_class or "unknown")
        if ph_range is not None:
            values["ph_min"], values["ph_max"] = ph_range

        drainage = DRAINAGE_FROM_SURVEY.get(self.drainage_class or "")
        if drainage:
            values.update(drainage)

        organic = ORGANIC_INPUT_FROM_SURVEY.get(self.organic_input or "unknown")
        if organic:
            values["organic_matter_pct"] *= organic["om_multiplier"]
            values["initial_n_g_m2"] += organic["n_boost_g_m2"]
            values["initial_p_g_m2"] += organic["p_boost_g_m2"]
            values["initial_k_g_m2"] += organic["k_boost_g_m2"]

        return SoilProfile(**values)

    @property
    def is_empty(self) -> bool:
        return not any([self.ph_class, self.drainage_class, self.organic_input, self.last_season_quality])


def plot_calibration_score(plot_overrides: PlotOverrides | None) -> int:
    if plot_overrides is None:
        return 50
    score = 50
    if plot_overrides.ph_class and plot_overrides.ph_class != "unknown":
        score += 20
    if plot_overrides.drainage_class:
        score += 10
    if plot_overrides.organic_input and plot_overrides.organic_input != "unknown":
        score += 15
    if plot_overrides.last_season_quality:
        score += 5
    return min(100, score)


SOIL_PROFILES: dict[str, SoilProfile] = {
    "sand": SoilProfile(
        id="sand",
        label="\u041f\u0456\u0449\u0430\u043d\u0438\u0439",
        field_capacity_mm_per_m=120,
        wilting_point_mm_per_m=45,
        ph_min=5.8,
        ph_max=7.0,
        organic_matter_pct=1.0,
        bulk_density_g_cm3=1.55,
        drainage_class="excessive",
        effective_rain_multiplier=0.55,
        drainage_multiplier=1.35,
        disease_risk_multiplier=0.70,
        compaction_risk=0.15,
        infiltration_rate_mm_h=35.0,
        nutrient_retention=0.20,
        nitrogen_leaching_multiplier=1.45,
        phosphorus_fixation_risk=0.15,
        potassium_retention=0.25,
        salinity_risk=0.25,
        waterlogging_risk=0.05,
        aeration_risk=0.05,
        initial_n_g_m2=2.0,
        initial_p_g_m2=1.5,
        initial_k_g_m2=2.2,
        initial_mg_g_m2=0.7,
        initial_ca_g_m2=6.0,
    ),
    "loamy_sand": SoilProfile(
        id="loamy_sand",
        label="\u0421\u0443\u043f\u0456\u0449\u0430\u043d\u0438\u0439",
        field_capacity_mm_per_m=160,
        wilting_point_mm_per_m=65,
        ph_min=5.8,
        ph_max=7.1,
        organic_matter_pct=1.5,
        bulk_density_g_cm3=1.50,
        drainage_class="fast",
        effective_rain_multiplier=0.70,
        drainage_multiplier=1.20,
        disease_risk_multiplier=0.80,
        compaction_risk=0.20,
        infiltration_rate_mm_h=25.0,
        nutrient_retention=0.30,
        nitrogen_leaching_multiplier=1.30,
        phosphorus_fixation_risk=0.18,
        potassium_retention=0.35,
        salinity_risk=0.25,
        waterlogging_risk=0.08,
        aeration_risk=0.08,
        initial_n_g_m2=2.8,
        initial_p_g_m2=2.0,
        initial_k_g_m2=3.2,
        initial_mg_g_m2=1.0,
        initial_ca_g_m2=8.0,
    ),
    "sandy_loam": SoilProfile(
        id="sandy_loam",
        label="\u041b\u0435\u0433\u043a\u0438\u0439 \u0441\u0443\u0433\u043b\u0438\u043d\u043e\u043a",
        field_capacity_mm_per_m=220,
        wilting_point_mm_per_m=95,
        ph_min=6.0,
        ph_max=7.2,
        organic_matter_pct=2.3,
        bulk_density_g_cm3=1.45,
        drainage_class="good",
        effective_rain_multiplier=0.82,
        drainage_multiplier=1.10,
        disease_risk_multiplier=0.90,
        compaction_risk=0.25,
        infiltration_rate_mm_h=18.0,
        nutrient_retention=0.45,
        nitrogen_leaching_multiplier=1.15,
        phosphorus_fixation_risk=0.22,
        potassium_retention=0.45,
        salinity_risk=0.22,
        waterlogging_risk=0.15,
        aeration_risk=0.15,
        initial_n_g_m2=4.2,
        initial_p_g_m2=3.2,
        initial_k_g_m2=5.0,
        initial_mg_g_m2=1.5,
        initial_ca_g_m2=12.0,
    ),
    "loam": DEFAULT_SOIL_PROFILE,
    "silt_loam": SoilProfile(
        id="silt_loam",
        label="\u041c\u0443\u043b\u043a\u0438\u0439 \u0441\u0443\u0433\u043b\u0438\u043d\u043e\u043a",
        field_capacity_mm_per_m=330,
        wilting_point_mm_per_m=155,
        ph_min=6.1,
        ph_max=7.4,
        organic_matter_pct=3.8,
        bulk_density_g_cm3=1.30,
        drainage_class="moderate",
        effective_rain_multiplier=1.05,
        drainage_multiplier=0.95,
        disease_risk_multiplier=1.05,
        compaction_risk=0.45,
        infiltration_rate_mm_h=9.0,
        nutrient_retention=0.68,
        nitrogen_leaching_multiplier=0.92,
        phosphorus_fixation_risk=0.30,
        potassium_retention=0.68,
        salinity_risk=0.25,
        waterlogging_risk=0.35,
        aeration_risk=0.35,
        initial_n_g_m2=6.5,
        initial_p_g_m2=5.0,
        initial_k_g_m2=7.5,
        initial_mg_g_m2=2.5,
        initial_ca_g_m2=18.0,
    ),
    "clay_loam": SoilProfile(
        id="clay_loam",
        label="\u0412\u0430\u0436\u043a\u0438\u0439 \u0441\u0443\u0433\u043b\u0438\u043d\u043e\u043a",
        field_capacity_mm_per_m=350,
        wilting_point_mm_per_m=185,
        ph_min=6.2,
        ph_max=7.5,
        organic_matter_pct=3.6,
        bulk_density_g_cm3=1.38,
        drainage_class="slow",
        effective_rain_multiplier=0.95,
        drainage_multiplier=0.82,
        disease_risk_multiplier=1.20,
        compaction_risk=0.60,
        infiltration_rate_mm_h=6.0,
        nutrient_retention=0.75,
        nitrogen_leaching_multiplier=0.82,
        phosphorus_fixation_risk=0.38,
        potassium_retention=0.78,
        salinity_risk=0.30,
        waterlogging_risk=0.55,
        aeration_risk=0.55,
        initial_n_g_m2=6.2,
        initial_p_g_m2=4.8,
        initial_k_g_m2=8.8,
        initial_mg_g_m2=2.8,
        initial_ca_g_m2=20.0,
    ),
    "clay": SoilProfile(
        id="clay",
        label="\u0413\u043b\u0438\u043d\u0438\u0441\u0442\u0438\u0439",
        field_capacity_mm_per_m=380,
        wilting_point_mm_per_m=220,
        ph_min=6.3,
        ph_max=7.7,
        organic_matter_pct=3.2,
        bulk_density_g_cm3=1.42,
        drainage_class="very_slow",
        effective_rain_multiplier=0.82,
        drainage_multiplier=0.70,
        disease_risk_multiplier=1.40,
        compaction_risk=0.75,
        infiltration_rate_mm_h=3.0,
        nutrient_retention=0.85,
        nitrogen_leaching_multiplier=0.70,
        phosphorus_fixation_risk=0.48,
        potassium_retention=0.88,
        salinity_risk=0.35,
        waterlogging_risk=0.75,
        aeration_risk=0.75,
        initial_n_g_m2=5.2,
        initial_p_g_m2=4.0,
        initial_k_g_m2=9.5,
        initial_mg_g_m2=3.0,
        initial_ca_g_m2=22.0,
    ),
    "peat": SoilProfile(
        id="peat",
        label="\u0422\u043e\u0440\u0444'\u044f\u043d\u0438\u0439",
        field_capacity_mm_per_m=520,
        wilting_point_mm_per_m=160,
        ph_min=4.8,
        ph_max=6.5,
        organic_matter_pct=18.0,
        bulk_density_g_cm3=0.55,
        drainage_class="variable",
        effective_rain_multiplier=1.10,
        drainage_multiplier=0.85,
        disease_risk_multiplier=1.30,
        compaction_risk=0.30,
        infiltration_rate_mm_h=12.0,
        nutrient_retention=0.70,
        nitrogen_leaching_multiplier=0.95,
        phosphorus_fixation_risk=0.35,
        potassium_retention=0.55,
        salinity_risk=0.15,
        waterlogging_risk=0.65,
        aeration_risk=0.55,
        initial_n_g_m2=7.0,
        initial_p_g_m2=3.5,
        initial_k_g_m2=5.5,
        initial_mg_g_m2=2.0,
        initial_ca_g_m2=10.0,
    ),
    "chernozem": SoilProfile(
        id="chernozem",
        label="\u0427\u043e\u0440\u043d\u043e\u0437\u0435\u043c",
        field_capacity_mm_per_m=360,
        wilting_point_mm_per_m=150,
        ph_min=6.3,
        ph_max=7.5,
        organic_matter_pct=5.5,
        bulk_density_g_cm3=1.20,
        drainage_class="good",
        effective_rain_multiplier=1.0,
        drainage_multiplier=0.95,
        disease_risk_multiplier=0.90,
        compaction_risk=0.35,
        infiltration_rate_mm_h=10.0,
        nutrient_retention=0.82,
        nitrogen_leaching_multiplier=0.85,
        phosphorus_fixation_risk=0.25,
        potassium_retention=0.82,
        salinity_risk=0.20,
        waterlogging_risk=0.25,
        aeration_risk=0.20,
        initial_n_g_m2=9.0,
        initial_p_g_m2=6.5,
        initial_k_g_m2=10.0,
        initial_mg_g_m2=3.2,
        initial_ca_g_m2=20.0,
    ),
}


def get_soil_profile(soil_type: str | None, plot_overrides: PlotOverrides | None = None) -> SoilProfile:
    soil = SOIL_PROFILES.get(soil_type or DEFAULT_SOIL_PROFILE.id, DEFAULT_SOIL_PROFILE)
    if plot_overrides is None or plot_overrides.is_empty:
        return soil
    return plot_overrides.apply_to(soil)


def list_soil_profiles() -> list[SoilProfile]:
    return list(SOIL_PROFILES.values())


def list_soil_profile_dicts() -> list[dict]:
    return [profile.to_dict() for profile in list_soil_profiles()]
