"""Curated protection profile catalog for disease-risk recommendations."""
from __future__ import annotations

from app.services.protection_profile import ProtectionProfile, ProtectionRecommendation


PROTECTION_PROFILES: dict[str, ProtectionProfile] = {
    "contact_copper": ProtectionProfile(
        id="contact_copper",
        label="\u041a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u043c\u0456\u0434\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442",
        protection_type="\u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["late_blight", "downy_mildew", "bacterial_spot"],
        frac_group="M01",
        mode_of_action="\u0431\u0430\u0433\u0430\u0442\u043e\u0434\u0456\u043b\u044f\u043d\u043a\u043e\u0432\u0438\u0439 \u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439",
        reentry_days=1,
        pre_harvest_interval_days=7,
        rainfast_hours=4,
        max_applications_per_season=4,
        min_interval_days=7,
        preventive=True,
        curative=False,
        notes=["\u041a\u0440\u0430\u0449\u0435 \u0434\u043e \u043f\u0435\u0440\u0456\u043e\u0434\u0443 \u0442\u0440\u0438\u0432\u0430\u043b\u043e\u0457 \u0432\u043e\u043b\u043e\u0433\u0438"],
    ),
    "copper_oxychloride": ProtectionProfile(
        id="copper_oxychloride",
        label="\u041e\u043a\u0441\u0438\u0445\u043b\u043e\u0440\u0438\u0434 \u043c\u0456\u0434\u0456",
        protection_type="\u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["late_blight", "downy_mildew", "alternaria"],
        frac_group="M01",
        mode_of_action="\u0431\u0430\u0433\u0430\u0442\u043e\u0434\u0456\u043b\u044f\u043d\u043a\u043e\u0432\u0438\u0439 \u043c\u0456\u0434\u043d\u0438\u0439 \u043a\u043e\u043d\u0442\u0430\u043a\u0442",
        reentry_days=1,
        pre_harvest_interval_days=7,
        rainfast_hours=4,
        max_applications_per_season=4,
        min_interval_days=7,
        preventive=True,
        curative=False,
    ),
    "copper_hydroxide": ProtectionProfile(
        id="copper_hydroxide",
        label="\u0413\u0456\u0434\u0440\u043e\u043a\u0441\u0438\u0434 \u043c\u0456\u0434\u0456",
        protection_type="\u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["downy_mildew", "late_blight", "bacterial_spot"],
        frac_group="M01",
        mode_of_action="\u0437\u0430\u0445\u0438\u0441\u043d\u0430 \u043c\u0456\u0434\u043d\u0430 \u043f\u043b\u0456\u0432\u043a\u0430",
        reentry_days=1,
        pre_harvest_interval_days=7,
        rainfast_hours=4,
        max_applications_per_season=4,
        min_interval_days=7,
    ),
    "mancozeb_contact": ProtectionProfile(
        id="mancozeb_contact",
        label="\u041c\u0430\u043d\u043a\u043e\u0446\u0435\u0431",
        protection_type="\u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["late_blight", "downy_mildew", "alternaria", "rust"],
        frac_group="M03",
        mode_of_action="\u0431\u0430\u0433\u0430\u0442\u043e\u0434\u0456\u043b\u044f\u043d\u043a\u043e\u0432\u0438\u0439",
        reentry_days=1,
        pre_harvest_interval_days=20,
        rainfast_hours=6,
        max_applications_per_season=4,
        min_interval_days=7,
        preventive=True,
        curative=False,
        notes=["\u0414\u043e\u0440\u0435\u0447\u043d\u0438\u0439 \u0434\u043b\u044f \u043f\u0440\u043e\u0444\u0456\u043b\u0430\u043a\u0442\u0438\u043a\u0438 \u043f\u0440\u0438 \u0441\u0442\u0456\u0439\u043a\u043e\u043c\u0443 \u0432\u043e\u043b\u043e\u0433\u043e\u043c\u0443 \u0432\u0456\u043a\u043d\u0456"],
    ),
    "chlorothalonil_contact": ProtectionProfile(
        id="chlorothalonil_contact",
        label="\u0425\u043b\u043e\u0440\u043e\u0442\u0430\u043b\u043e\u043d\u0456\u043b",
        protection_type="\u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["alternaria", "botrytis", "late_blight"],
        frac_group="M05",
        mode_of_action="\u0431\u0430\u0433\u0430\u0442\u043e\u0434\u0456\u043b\u044f\u043d\u043a\u043e\u0432\u0438\u0439",
        reentry_days=1,
        pre_harvest_interval_days=14,
        rainfast_hours=4,
        max_applications_per_season=3,
        min_interval_days=7,
        notes=["\u041f\u0435\u0440\u0435\u0432\u0456\u0440\u044f\u0439\u0442\u0435 \u0434\u043e\u0437\u0432\u0456\u043b \u0434\u043b\u044f \u043a\u0443\u043b\u044c\u0442\u0443\u0440\u0438 \u0442\u0430 \u0440\u0435\u0433\u0456\u043e\u043d\u0443"],
    ),
    "systemic_oomycete": ProtectionProfile(
        id="systemic_oomycete",
        label="\u0421\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442 \u0432\u0456\u0434 \u043e\u043e\u043c\u0456\u0446\u0435\u0442\u0456\u0432",
        protection_type="\u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["late_blight", "downy_mildew"],
        frac_group="40",
        mode_of_action="\u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439 / \u0442\u0440\u0430\u043d\u0441\u043b\u0430\u043c\u0456\u043d\u0430\u0440\u043d\u0438\u0439",
        reentry_days=2,
        pre_harvest_interval_days=14,
        rainfast_hours=2,
        max_applications_per_season=2,
        min_interval_days=10,
        preventive=True,
        curative=True,
        notes=["\u0420\u043e\u0442\u0443\u0439\u0442\u0435 FRAC-\u0433\u0440\u0443\u043f\u0438, \u043d\u0435 \u043f\u043e\u0432\u0442\u043e\u0440\u044e\u0439\u0442\u0435 \u043e\u0434\u043d\u0443 \u0433\u0440\u0443\u043f\u0443 \u043f\u043e\u0441\u043f\u0456\u043b\u044c"],
    ),
    "phosphonate_oomycete": ProtectionProfile(
        id="phosphonate_oomycete",
        label="\u0424\u043e\u0441\u0444\u043e\u043d\u0430\u0442\u0438 \u0432\u0456\u0434 \u043e\u043e\u043c\u0456\u0446\u0435\u0442\u0456\u0432",
        protection_type="\u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["downy_mildew", "late_blight"],
        frac_group="P07",
        mode_of_action="\u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439, \u0456\u043d\u0434\u0443\u043a\u0446\u0456\u044f \u0437\u0430\u0445\u0438\u0441\u0442\u0443",
        reentry_days=1,
        pre_harvest_interval_days=7,
        rainfast_hours=2,
        max_applications_per_season=3,
        min_interval_days=10,
        preventive=True,
        curative=True,
    ),
    "azoxystrobin_qoi": ProtectionProfile(
        id="azoxystrobin_qoi",
        label="\u0410\u0437\u043e\u043a\u0441\u0438\u0441\u0442\u0440\u043e\u0431\u0456\u043d",
        protection_type="\u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["powdery_mildew", "alternaria", "rust"],
        frac_group="11",
        mode_of_action="QoI",
        reentry_days=1,
        pre_harvest_interval_days=7,
        rainfast_hours=2,
        max_applications_per_season=2,
        min_interval_days=10,
        preventive=True,
        curative=False,
        notes=["\u0412\u0438\u0441\u043e\u043a\u0438\u0439 \u0440\u0438\u0437\u0438\u043a \u0440\u0435\u0437\u0438\u0441\u0442\u0435\u043d\u0442\u043d\u043e\u0441\u0442\u0456: \u0440\u043e\u0442\u0430\u0446\u0456\u044f FRAC \u043e\u0431\u043e\u0432'\u044f\u0437\u043a\u043e\u0432\u0430"],
    ),
    "propiconazole_dmi": ProtectionProfile(
        id="propiconazole_dmi",
        label="\u041f\u0440\u043e\u043f\u0456\u043a\u043e\u043d\u0430\u0437\u043e\u043b",
        protection_type="\u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["powdery_mildew", "rust"],
        frac_group="3",
        mode_of_action="DMI",
        reentry_days=1,
        pre_harvest_interval_days=14,
        rainfast_hours=2,
        max_applications_per_season=2,
        min_interval_days=10,
        preventive=True,
        curative=True,
    ),
    "difenoconazole_dmi": ProtectionProfile(
        id="difenoconazole_dmi",
        label="\u0414\u0438\u0444\u0435\u043d\u043e\u043a\u043e\u043d\u0430\u0437\u043e\u043b",
        protection_type="\u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["alternaria", "powdery_mildew", "rust"],
        frac_group="3",
        mode_of_action="DMI",
        reentry_days=1,
        pre_harvest_interval_days=14,
        rainfast_hours=2,
        max_applications_per_season=2,
        min_interval_days=10,
        preventive=True,
        curative=True,
    ),
    "sulfur_contact": ProtectionProfile(
        id="sulfur_contact",
        label="\u0421\u0456\u0440\u043a\u0430 / \u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442",
        protection_type="\u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["powdery_mildew", "rust"],
        frac_group="M02",
        mode_of_action="\u0431\u0430\u0433\u0430\u0442\u043e\u0434\u0456\u043b\u044f\u043d\u043a\u043e\u0432\u0438\u0439",
        reentry_days=1,
        pre_harvest_interval_days=5,
        rainfast_hours=3,
        max_applications_per_season=5,
        min_interval_days=7,
        preventive=True,
        curative=False,
        max_temp_c=26,
        notes=["\u041d\u0435 \u0437\u0430\u0441\u0442\u043e\u0441\u043e\u0432\u0443\u0439\u0442\u0435 \u0443 \u0441\u043f\u0435\u043a\u0443"],
    ),
    "potassium_bicarbonate": ProtectionProfile(
        id="potassium_bicarbonate",
        label="\u041a\u0430\u043b\u0456\u0439 \u0431\u0456\u043a\u0430\u0440\u0431\u043e\u043d\u0430\u0442",
        protection_type="\u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442",
        target_diseases=["powdery_mildew"],
        frac_group="NC",
        mode_of_action="\u0437\u043c\u0456\u043d\u0430 pH \u043d\u0430 \u043f\u043e\u0432\u0435\u0440\u0445\u043d\u0456 \u043b\u0438\u0441\u0442\u044f",
        reentry_days=0,
        pre_harvest_interval_days=1,
        rainfast_hours=1,
        max_applications_per_season=5,
        min_interval_days=5,
        preventive=True,
        curative=True,
    ),
    "bacillus_biocontrol": ProtectionProfile(
        id="bacillus_biocontrol",
        label="\u0411\u0456\u043e\u043a\u043e\u043d\u0442\u0440\u043e\u043b\u044c Bacillus",
        protection_type="\u0431\u0456\u043e\u043b\u043e\u0433\u0456\u0447\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442",
        target_diseases=["powdery_mildew", "botrytis", "alternaria", "fusarium", "observed_symptoms"],
        frac_group="BM02",
        mode_of_action="\u043a\u043e\u043d\u043a\u0443\u0440\u0435\u043d\u0446\u0456\u044f \u0442\u0430 \u0430\u043d\u0442\u0430\u0433\u043e\u043d\u0456\u0437\u043c",
        reentry_days=0,
        pre_harvest_interval_days=0,
        rainfast_hours=1,
        max_applications_per_season=8,
        min_interval_days=5,
        preventive=True,
        curative=False,
        max_temp_c=30,
        notes=["\u0414\u043e\u0440\u0435\u0447\u043d\u0438\u0439 \u0434\u043b\u044f \u043c'\u044f\u043a\u043e\u0457 \u043f\u0440\u043e\u0444\u0456\u043b\u0430\u043a\u0442\u0438\u043a\u0438 \u0442\u0430 \u0456\u043d\u0442\u0435\u0433\u0440\u043e\u0432\u0430\u043d\u043e\u0433\u043e \u0437\u0430\u0445\u0438\u0441\u0442\u0443"],
    ),
    "fusarium_soil_biocontrol": ProtectionProfile(
        id="fusarium_soil_biocontrol",
        label="Біозахист ґрунту від фузаріозу",
        protection_type="біологічний ґрунтовий захист",
        target_diseases=["fusarium"],
        frac_group="BM",
        mode_of_action="антагонізм у ризосфері, пригнічення ґрунтового інокулюму",
        reentry_days=0,
        pre_harvest_interval_days=0,
        rainfast_hours=0,
        max_applications_per_season=6,
        min_interval_days=10,
        preventive=True,
        curative=False,
        notes=[
            "Фузаріоз часто судинний/ґрунтовий: листкове обприскування не лікує уражену рослину",
            "Працює як профілактика: сівозміна, дренаж, видалення уражених решток, біопрепарати у ґрунт",
        ],
    ),
    "botrytis_contact": ProtectionProfile(
        id="botrytis_contact",
        label="\u041f\u0440\u043e\u0442\u0438\u0433\u043d\u0438\u043b\u044c\u043d\u0438\u0439 \u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0437\u0430\u0445\u0438\u0441\u0442",
        protection_type="\u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["botrytis"],
        frac_group="M",
        mode_of_action="\u043f\u0440\u043e\u0444\u0456\u043b\u0430\u043a\u0442\u0438\u0447\u043d\u0438\u0439 \u043a\u043e\u043d\u0442\u0430\u043a\u0442\u043d\u0438\u0439",
        reentry_days=1,
        pre_harvest_interval_days=7,
        rainfast_hours=4,
        max_applications_per_season=3,
        min_interval_days=7,
        preventive=True,
        curative=False,
        notes=["\u041f\u043e\u0454\u0434\u043d\u0443\u0439\u0442\u0435 \u0437 \u043f\u0440\u043e\u0432\u0456\u0442\u0440\u044e\u0432\u0430\u043d\u043d\u044f\u043c \u043f\u043e\u0441\u0430\u0434\u043e\u043a"],
    ),
    "botrytis_sdhi": ProtectionProfile(
        id="botrytis_sdhi",
        label="SDHI \u043f\u0440\u043e\u0442\u0438 Botrytis",
        protection_type="\u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0438\u0439 \u0444\u0443\u043d\u0433\u0456\u0446\u0438\u0434",
        target_diseases=["botrytis"],
        frac_group="7",
        mode_of_action="SDHI",
        reentry_days=1,
        pre_harvest_interval_days=7,
        rainfast_hours=2,
        max_applications_per_season=2,
        min_interval_days=10,
        preventive=True,
        curative=True,
    ),
}


def get_protection_profile(profile_id: str) -> ProtectionProfile:
    return PROTECTION_PROFILES[profile_id]


def list_protection_profiles() -> list[ProtectionProfile]:
    return list(PROTECTION_PROFILES.values())


def list_protection_profile_dicts() -> list[dict]:
    return [profile.to_dict() for profile in list_protection_profiles()]


def recommend_protection(disease: str, risk_level: float) -> ProtectionRecommendation:
    if disease in {"late_blight", "downy_mildew"}:
        if risk_level >= 0.75:
            profile_id = "systemic_oomycete"
        elif risk_level >= 0.5:
            profile_id = "mancozeb_contact"
        else:
            profile_id = "contact_copper"
    elif disease == "powdery_mildew":
        if risk_level >= 0.7:
            profile_id = "azoxystrobin_qoi"
        elif risk_level >= 0.45:
            profile_id = "sulfur_contact"
        else:
            profile_id = "potassium_bicarbonate"
    elif disease == "botrytis":
        profile_id = "botrytis_sdhi" if risk_level >= 0.65 else "botrytis_contact"
    elif disease == "alternaria":
        profile_id = "azoxystrobin_qoi" if risk_level >= 0.65 else "mancozeb_contact"
    elif disease == "rust":
        profile_id = "propiconazole_dmi" if risk_level >= 0.6 else "sulfur_contact"
    elif disease == "fusarium":
        profile_id = "fusarium_soil_biocontrol"
    elif disease == "observed_symptoms":
        profile_id = "bacillus_biocontrol" if risk_level < 0.65 else "contact_copper"
    else:
        profile_id = "bacillus_biocontrol" if risk_level < 0.45 else "contact_copper"

    profile = get_protection_profile(profile_id)
    reasons = [
        f"\u0422\u0438\u043f \u0437\u0430\u0445\u0438\u0441\u0442\u0443: {profile.protection_type}",
        f"FRAC: {profile.frac_group}",
        f"REI: {profile.reentry_days} \u0434\u043d.",
        f"PHI: {profile.pre_harvest_interval_days} \u0434\u043d.",
        f"\u0414\u043e\u0449\u043e\u0441\u0442\u0456\u0439\u043a\u0456\u0441\u0442\u044c: {profile.rainfast_hours} \u0433\u043e\u0434.",
    ]
    if profile.curative:
        reasons.append("\u041f\u0440\u043e\u0444\u0456\u043b\u044c \u043c\u0430\u0454 \u0441\u0438\u0441\u0442\u0435\u043c\u043d\u0443/\u043a\u0443\u0440\u0430\u0442\u0438\u0432\u043d\u0443 \u0434\u0456\u044e")
    reasons.extend(profile.notes)

    explanation = (
        f"\u041e\u0431\u0440\u0430\u043d\u043e {profile.label.lower()}: "
        f"{profile.protection_type}, FRAC {profile.frac_group}, "
        f"REI {profile.reentry_days} \u0434\u043d., PHI {profile.pre_harvest_interval_days} \u0434\u043d."
    )
    return ProtectionRecommendation(disease=disease, profile=profile, explanation=explanation, reasons=reasons)
