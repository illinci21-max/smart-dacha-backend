"""Curated fertilizer profile catalog for agro-analysis recommendations."""
from __future__ import annotations

from app.services.fertilizer_profile import FertilizerProfile, FertilizerRecommendation
from app.services.soil_profile import SoilProfile


FERTILIZER_PROFILES: dict[str, FertilizerProfile] = {
    "root_phosphorus": FertilizerProfile(
        id="root_phosphorus",
        label="\u0421\u0442\u0430\u0440\u0442\u043e\u0432\u0435 \u0444\u043e\u0441\u0444\u043e\u0440\u043d\u0435",
        fertilizer_type="\u043c\u0456\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u0435",
        application_method="\u043a\u043e\u0440\u0435\u043d\u0435\u0432\u0435",
        p_pct=20,
        release_speed="medium",
        leaching_risk=0.25,
        salt_index=0.35,
        suitable_goals=["root_start"],
        avoid_before_rain_mm=15,
    ),
    "nitrogen_growth": FertilizerProfile(
        id="nitrogen_growth",
        label="\u0410\u0437\u043e\u0442\u043d\u0435 \u0434\u043b\u044f \u0440\u043e\u0441\u0442\u0443",
        fertilizer_type="\u043c\u0456\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u0435",
        application_method="\u043a\u043e\u0440\u0435\u043d\u0435\u0432\u0435",
        n_pct=20,
        release_speed="fast",
        leaching_risk=0.80,
        salt_index=0.65,
        suitable_goals=["vegetative_growth"],
        avoid_before_rain_mm=8,
    ),
    "pk_fruiting": FertilizerProfile(
        id="pk_fruiting",
        label="\u0424\u043e\u0441\u0444\u043e\u0440\u043d\u043e-\u043a\u0430\u043b\u0456\u0439\u043d\u0435",
        fertilizer_type="\u043c\u0456\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u0435",
        application_method="\u043a\u043e\u0440\u0435\u043d\u0435\u0432\u0435",
        p_pct=12,
        k_pct=24,
        release_speed="medium",
        leaching_risk=0.30,
        salt_index=0.45,
        suitable_goals=["flowering_fruiting"],
        avoid_before_rain_mm=12,
    ),
    "calcium_magnesium": FertilizerProfile(
        id="calcium_magnesium",
        label="\u041a\u0430\u043b\u044c\u0446\u0456\u0439 + \u043c\u0430\u0433\u043d\u0456\u0439",
        fertilizer_type="\u043c\u0456\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u0435",
        application_method="\u043a\u043e\u0440\u0435\u043d\u0435\u0432\u0435",
        mg_pct=10,
        ca_pct=15,
        release_speed="medium",
        leaching_risk=0.55,
        salt_index=0.40,
        suitable_goals=["leaching_recovery"],
        avoid_before_rain_mm=8,
    ),
    "compost": FertilizerProfile(
        id="compost",
        label="\u041a\u043e\u043c\u043f\u043e\u0441\u0442 / \u0431\u0456\u043e\u0433\u0443\u043c\u0443\u0441",
        fertilizer_type="\u043e\u0440\u0433\u0430\u043d\u0456\u043a\u0430",
        application_method="\u043f\u0456\u0434 \u043a\u043e\u0440\u0456\u043d\u044c / \u043c\u0443\u043b\u044c\u0447\u0430",
        n_pct=1.5,
        p_pct=0.8,
        k_pct=1.2,
        organic_matter_pct=35,
        release_speed="slow",
        leaching_risk=0.15,
        salt_index=0.15,
        suitable_goals=["soil_support", "root_start", "vegetative_growth"],
        avoid_before_rain_mm=25,
        max_temp_c=35,
        max_wind_ms=10,
    ),
    "foliar_micro": FertilizerProfile(
        id="foliar_micro",
        label="\u041b\u0438\u0441\u0442\u043a\u043e\u0432\u0435 \u043c\u0456\u043a\u0440\u043e",
        fertilizer_type="\u043b\u0438\u0441\u0442\u043a\u043e\u0432\u0435",
        application_method="\u043f\u043e \u043b\u0438\u0441\u0442\u0443",
        mg_pct=3,
        ca_pct=5,
        release_speed="fast",
        leaching_risk=0.05,
        salt_index=0.25,
        suitable_goals=["quick_correction"],
        avoid_before_rain_mm=2,
        max_temp_c=26,
        max_wind_ms=4,
        requires_soil_moisture=False,
    ),
}


def get_fertilizer_profile(profile_id: str) -> FertilizerProfile:
    return FERTILIZER_PROFILES[profile_id]


def list_fertilizer_profiles() -> list[FertilizerProfile]:
    return list(FERTILIZER_PROFILES.values())


def list_fertilizer_profile_dicts() -> list[dict]:
    return [profile.to_dict() for profile in list_fertilizer_profiles()]


def recommend_fertilizer(
    goal: str,
    soil: SoilProfile,
    *,
    nitrogen_g_m2: float = 0.0,
    phosphorus_g_m2: float = 0.0,
    potassium_g_m2: float = 0.0,
    magnesium_g_m2: float = 0.0,
    calcium_g_m2: float = 0.0,
) -> FertilizerRecommendation:
    profile_id = {
        "root_start": "root_phosphorus",
        "vegetative_growth": "nitrogen_growth",
        "flowering_fruiting": "pk_fruiting",
        "leaching_recovery": "calcium_magnesium",
    }.get(goal, "compost")
    profile = get_fertilizer_profile(profile_id)

    parts = []
    if nitrogen_g_m2:
        parts.append(f"N {nitrogen_g_m2:.1f}\u0433")
    if phosphorus_g_m2:
        parts.append(f"P {phosphorus_g_m2:.1f}\u0433")
    if potassium_g_m2:
        parts.append(f"K {potassium_g_m2:.1f}\u0433")
    if magnesium_g_m2:
        parts.append(f"Mg {magnesium_g_m2:.1f}\u0433")
    if calcium_g_m2:
        parts.append(f"Ca {calcium_g_m2:.1f}\u0433")
    amount = " + ".join(parts) if parts else profile.nutrient_label

    reasons = [
        f"\u0422\u0438\u043f \u0434\u043e\u0431\u0440\u0438\u0432\u0430: {profile.label}",
        f"\u0424\u043e\u0440\u043c\u0430: {profile.fertilizer_type}, {profile.application_method}",
        f"\u0423\u0442\u0440\u0438\u043c\u0430\u043d\u043d\u044f \u043f\u043e\u0436\u0438\u0432\u043d\u0438\u0445 \u0491\u0440\u0443\u043d\u0442\u043e\u043c: {soil.nutrient_retention * 100:.0f}%",
    ]
    if soil.nitrogen_leaching_multiplier > 1.15 and nitrogen_g_m2:
        reasons.append("\u041d\u0430 \u0446\u044c\u043e\u043c\u0443 \u0491\u0440\u0443\u043d\u0442\u0456 \u0430\u0437\u043e\u0442 \u043a\u0440\u0430\u0449\u0435 \u0434\u0430\u0432\u0430\u0442\u0438 \u0434\u0440\u0456\u0431\u043d\u0456\u0448\u0438\u043c\u0438 \u0434\u043e\u0437\u0430\u043c\u0438")
    if soil.phosphorus_fixation_risk > 0.35 and phosphorus_g_m2:
        reasons.append("\u0420\u0438\u0437\u0438\u043a \u0444\u0456\u043a\u0441\u0430\u0446\u0456\u0457 \u0444\u043e\u0441\u0444\u043e\u0440\u0443: \u043a\u0440\u0430\u0449\u0435 \u043b\u043e\u043a\u0430\u043b\u044c\u043d\u0435 \u0432\u043d\u0435\u0441\u0435\u043d\u043d\u044f")

    explanation = (
        f"\u041e\u0431\u0440\u0430\u043d\u043e {profile.label.lower()} "
        f"({profile.fertilizer_type}, {profile.application_method}). "
        f"\u041e\u0440\u0456\u0454\u043d\u0442\u0438\u0440: {amount} \u043d\u0430 1 \u043c\u00b2."
    )
    return FertilizerRecommendation(goal=goal, profile=profile, amount=amount, explanation=explanation, reasons=reasons)
