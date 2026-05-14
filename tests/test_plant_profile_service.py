from app.services.plant_profile_service import _normalize_name, sanitize_profile_data


def test_normalize_name_keeps_common_crop_stems():
    assert _normalize_name("Томати") == "томат"
    assert _normalize_name("  ПОМІДОРИ  ") == "томат"
    assert _normalize_name("Огірки") == "огірок"
    assert _normalize_name("картошка") == "картопля"


def test_sanitize_profile_data_clamps_and_repairs_invalid_ranges():
    profile = sanitize_profile_data(
        {
            "kc_initial": 2.5,
            "kc_mid": -1,
            "root_depth_initial_cm": 100,
            "root_depth_max_cm": 20,
            "field_capacity_mm": 80,
            "wilting_point_mm": 120,
            "t_min_growth": 30,
            "t_optimal_min": 25,
            "t_optimal_max": 15,
            "t_max_growth": 10,
            "days_to_harvest_min": 160,
            "days_to_harvest_max": 60,
        },
        "Тест",
        "Овочі",
        "gemini",
    )

    assert profile["kc_initial"] == 0.85
    assert profile["kc_mid"] == 0.45
    assert profile["root_depth_initial_cm"] <= profile["root_depth_max_cm"]
    assert profile["wilting_point_mm"] < profile["field_capacity_mm"]
    assert profile["t_min_growth"] < profile["t_optimal_min"]
    assert profile["t_optimal_min"] <= profile["t_optimal_max"]
    assert profile["t_optimal_max"] < profile["t_max_growth"]
    assert profile["days_to_harvest_min"] <= profile["days_to_harvest_max"]
    assert profile["profile_confidence"] < 70
    assert profile["confidence"] == profile["profile_confidence"]
    assert profile["validation_warnings"]


def test_sanitize_profile_data_keeps_agro_analysis_rules():
    profile = sanitize_profile_data(
        {
            "disease_protection_adaptation_days": 6,
            "disease_protection_early_symptom_days": 2,
            "biofungicide_allowed_from_day": 0,
            "chemical_fungicide_allowed_from_day": 6,
            "copper_fungicide_allowed_from_day": 8,
            "max_spray_temp_c": 27,
            "avoid_spray_before_rain_hours": 8,
            "cold_stress_threshold_c": 0,
            "frost_critical_threshold_c": -2,
        },
        "Raspberry",
        "Berries",
        "gemini",
    )

    assert profile["disease_protection_adaptation_days"] == 6
    assert profile["biofungicide_allowed_from_day"] == 0
    assert profile["chemical_fungicide_allowed_from_day"] == 6
    assert profile["copper_fungicide_allowed_from_day"] == 8
    assert profile["max_spray_temp_c"] == 27
    assert profile["avoid_spray_before_rain_hours"] == 8
    assert profile["cold_stress_threshold_c"] == 0
    assert profile["frost_critical_threshold_c"] == -2
