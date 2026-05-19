from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.services.fertilizer_profile_service import get_fertilizer_profile, recommend_fertilizer
from app.services.protection_profile_service import PROTECTION_PROFILES, recommend_protection
from app.services.soil_profile_service import PlotOverrides, SOIL_PROFILES, get_soil_profile, plot_calibration_score
from app.services.sat_service import compute_sat_with_topup
from app.services.smart_gardener_engine import (
    GrowthPhase,
    SmartGardenerEngine,
    _extraterrestrial_radiation,
    _psychrometric_constant,
    crop_profile_from_backend,
    generate_analysis,
    generate_tasks,
    parse_weather,
)


PROFILE = {
    "emoji": "🍅",
    "category": "Овочі",
    "initial_days": 25,
    "development_days": 35,
    "mid_season_days": 40,
    "late_season_days": 25,
    "kc_initial": 0.40,
    "kc_mid": 1.15,
    "kc_end": 0.70,
    "root_depth_initial_cm": 10,
    "root_depth_max_cm": 70,
    "field_capacity_mm": 200,
    "wilting_point_mm": 65,
    "critical_depletion": 0.50,
    "nitrogen": 2.5,
    "phosphorus": 1.0,
    "potassium": 2.0,
    "magnesium": 0.4,
    "calcium": 0.5,
    "t_base": 10,
    "t_max_growth": 38,
    "frost_tolerance": 1,
    "sus_late_blight": 0.85,
    "sus_powdery_mildew": 0.3,
    "sus_botrytis": 0.4,
    "days_to_harvest_min": 70,
    "days_to_harvest_max": 120,
}


def _weather(day: int, rain: float = 0, humidity: float = 65, temp_max: float = 28, temp_min: float = 17):
    return {
        "date": f"2026-04-{day:02d}",
        "temp_max": temp_max,
        "temp_min": temp_min,
        "temp_avg": (temp_max + temp_min) / 2,
        "precipitation": rain,
        "rain_probability": 10,
        "solar_radiation": 18,
        "wind_speed": 2.0,
        "humidity_avg": humidity,
        "humidity_max": humidity + 10,
        "cloud_cover": 45,
        "has_dew": False,
        "is_fog": False,
    }


def test_smart_engine_generates_rich_backend_shape():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-03-01", "category": "Овочі"}],
        {"Томат": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20),
        weather_history=[_weather(i) for i in range(1, 20)],
        weather_forecast=[_weather(21), _weather(22)],
        soil_type="loam",
    )

    assert tasks
    assert {"task_type", "title", "priority", "description", "action", "category", "confidence", "reasons"}.issubset(tasks[0])
    assert 45 <= tasks[0]["confidence"] <= 99
    assert isinstance(tasks[0]["reasons"], list)
    assert any(t["task_type"] in {"watering", "fertilizing", "disease_protection", "general"} for t in tasks)


def test_watering_action_cooldown_suppresses_watering():
    engine = SmartGardenerEngine()
    base = engine.calculate_grid_needs(
        grid_cells=[{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-03-01"}],
        profiles_map={"Томат": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=40, temp_max=34, temp_min=20),
        weather_history=[_weather(i, rain=0, humidity=40, temp_max=34, temp_min=20) for i in range(1, 20)],
    )
    with_action = engine.calculate_grid_needs(
        grid_cells=[{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-03-01"}],
        profiles_map={"Томат": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=40, temp_max=34, temp_min=20),
        weather_history=[_weather(i, rain=0, humidity=40, temp_max=34, temp_min=20) for i in range(1, 20)],
        user_actions=[{"action_type": "watering", "plant_type": "Томат", "scope": "all", "created_at": "2026-04-20T08:00:00+00:00"}],
    )

    assert any(t["task_type"] == "watering" for t in base["tasks"])
    assert not any(t["task_type"] == "watering" for t in with_action["tasks"])


def test_frost_forecast_detects_day_after_tomorrow_at_threshold():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-04-10", "category": "Овочі"}],
        {"Томат": {**PROFILE, "frost_tolerance": 0}},
        today=date(2026, 4, 20),
        weather_today=_weather(20, temp_max=15, temp_min=8),
        weather_forecast=[
            _weather(20, temp_max=15, temp_min=8),
            _weather(21, temp_max=12, temp_min=4),
            _weather(22, temp_max=10, temp_min=0),
        ],
        soil_type="loam",
    )

    assert any(
        t["task_type"] == "frost_protection"
        and "Заморозок післязавтра" in t["title"]
        and any("післязавтра 0°C" in reason for reason in t["reasons"])
        for t in tasks
    )


def test_gdd_missing_history_uses_history_average_not_today():
    engine = SmartGardenerEngine()
    gdd = engine.accumulate_gdd(
        history=[
            parse_weather(_weather(18, temp_max=25, temp_min=15)),
            parse_weather(_weather(19, temp_max=25, temp_min=15)),
        ],
        today_weather=parse_weather(_weather(20, temp_max=10, temp_min=10)),
        t_base=10,
        age_days=6,
    )

    assert gdd == 50.0


def test_gdd_uses_upper_temperature_cutoff():
    weather = parse_weather(_weather(20, temp_max=44, temp_min=24))

    uncapped = SmartGardenerEngine.calculate_daily_gdd(weather, t_base=10)
    capped = SmartGardenerEngine.calculate_daily_gdd(weather, t_base=10, t_upper=30)

    assert uncapped == 24.0
    assert capped == 17.0


def test_sat_hybrid_uses_db_baseline_when_batch_fresh():
    plant = SimpleNamespace(
        id="plant-1",
        sat_accumulated=425.0,
        sat_last_updated_at=date(2026, 5, 20),
        planted_date=date(2026, 4, 1),
    )
    profile = SimpleNamespace(t_base=10.0, t_max_growth=30.0)

    result = compute_sat_with_topup(plant, profile, {}, today=date(2026, 5, 20))

    assert result == 425.0


def test_sat_hybrid_tops_up_when_batch_stale():
    plant = SimpleNamespace(
        id="plant-1",
        sat_accumulated=400.0,
        sat_last_updated_at=date(2026, 5, 18),
        planted_date=date(2026, 4, 1),
    )
    profile = SimpleNamespace(t_base=10.0, t_max_growth=30.0)
    weather_cache = {
        date(2026, 5, 19): parse_weather({"temp_min": 14, "temp_max": 26}),
        date(2026, 5, 20): parse_weather({"temp_min": 15, "temp_max": 27}),
    }

    result = compute_sat_with_topup(plant, profile, weather_cache, today=date(2026, 5, 20))

    assert result == pytest.approx(421.0)


def test_sat_hybrid_caps_topup_at_14_days_with_warning(caplog):
    plant = SimpleNamespace(
        id="plant-1",
        sat_accumulated=100.0,
        sat_last_updated_at=date(2026, 4, 1),
        planted_date=date(2026, 3, 1),
    )
    profile = SimpleNamespace(t_base=10.0, t_max_growth=30.0)
    weather_cache = {
        date(2026, 4, day): parse_weather({"temp_min": 14, "temp_max": 26})
        for day in range(2, 16)
    }

    result = compute_sat_with_topup(plant, profile, weather_cache, today=date(2026, 5, 1))

    assert result == pytest.approx(240.0)
    assert "SAT batch is 30 days behind" in caplog.text


def test_sat_hybrid_falls_back_to_full_recompute_for_new_plant():
    plant = SimpleNamespace(
        id="plant-1",
        sat_accumulated=0.0,
        sat_last_updated_at=None,
        planted_date=date(2026, 5, 1),
    )
    profile = SimpleNamespace(t_base=10.0, t_max_growth=30.0)
    weather_cache = {
        date(2026, 5, day): parse_weather({"temp_min": 15, "temp_max": 27})
        for day in range(1, 6)
    }

    result = compute_sat_with_topup(plant, profile, weather_cache, today=date(2026, 5, 5))

    assert result == pytest.approx(55.0)


def test_engine_uses_sat_override_for_growth_phase_when_provided():
    engine = SmartGardenerEngine()
    today = date(2026, 4, 20)
    plant = engine._parse_grid_cells(
        [{"col": 1, "row": 2, "plant_type": "Tomato", "planted_date": "2026-04-01"}],
        today,
    )[0]
    profile = crop_profile_from_backend("Tomato", "Vegetables", PROFILE)

    engine._calculate_cell(
        plant,
        profile,
        et0_today=3.0,
        w_today=parse_weather(_weather(20, temp_max=16, temp_min=10)),
        w_forecast=[],
        w_history=[parse_weather(_weather(day, temp_max=16, temp_min=10)) for day in range(1, 20)],
        today=today,
        soil=get_soil_profile("loam"),
        latitude_deg=50.45,
        elevation_m=0.0,
        cumulative_gdd_override=1200.0,
    )

    assert plant.cumulative_gdd == 1200.0


def test_plot_overrides_acidic_ph_reduces_phosphorus_availability():
    soil = SOIL_PROFILES["chernozem"]
    adjusted = PlotOverrides(ph_class="acidic").apply_to(soil)

    p_default = SmartGardenerEngine._phosphorus_availability_factor(soil)
    p_acidic = SmartGardenerEngine._phosphorus_availability_factor(adjusted)

    assert p_acidic < p_default


def test_plot_overrides_heavy_organic_boosts_initial_pool():
    soil = SOIL_PROFILES["sand"]
    adjusted = PlotOverrides(organic_input="heavy").apply_to(soil)

    assert adjusted.initial_n_g_m2 == pytest.approx(soil.initial_n_g_m2 + 8.0)
    assert adjusted.initial_p_g_m2 == pytest.approx(soil.initial_p_g_m2 + 4.0)
    assert adjusted.initial_k_g_m2 == pytest.approx(soil.initial_k_g_m2 + 8.0)
    assert adjusted.organic_matter_pct == pytest.approx(soil.organic_matter_pct * 1.6)


def test_plot_overrides_fast_drainage_reduces_rain_retention():
    soil = SOIL_PROFILES["clay_loam"]
    adjusted = PlotOverrides(drainage_class="fast").apply_to(soil)

    assert adjusted.effective_rain_multiplier < soil.effective_rain_multiplier
    assert adjusted.waterlogging_risk < soil.waterlogging_risk


def test_plot_overrides_unknown_falls_back_to_catalog():
    soil = SOIL_PROFILES["loam"]
    adjusted = PlotOverrides(ph_class="unknown", organic_input="unknown").apply_to(soil)

    assert adjusted.ph_min == soil.ph_min
    assert adjusted.initial_n_g_m2 == soil.initial_n_g_m2


def test_calibration_confidence_score_grows_with_completeness():
    assert plot_calibration_score(PlotOverrides()) == 50
    assert plot_calibration_score(PlotOverrides(ph_class="neutral")) == 70
    assert plot_calibration_score(PlotOverrides(
        ph_class="neutral",
        drainage_class="moderate",
        organic_input="regular",
        last_season_quality="good",
    )) == 100


def test_open_meteo_wind_10m_is_converted_to_fao56_u2():
    weather = parse_weather({**_weather(20), "wind_speed": 10.0, "wind_height_m": 10})

    assert weather.wind_speed_ms == pytest.approx(7.48, abs=0.02)


def test_no_spray_wind_blocker_uses_converted_u2_threshold():
    engine = SmartGardenerEngine()
    windy = parse_weather({**_weather(21), "wind_speed": 7.0, "wind_height_m": 10})

    blockers = engine._application_blockers([windy])

    assert "сильний вітер" in blockers


def test_fao56_clear_sky_radiation_changes_with_season():
    engine = SmartGardenerEngine()
    winter = parse_weather({**_weather(15), "date": "2026-01-15", "solar_radiation": 10})
    summer = parse_weather({**_weather(15), "date": "2026-07-15", "solar_radiation": 10})

    assert engine.calculate_et0(summer, latitude_deg=50.45, elevation_m=0) > engine.calculate_et0(
        winter,
        latitude_deg=50.45,
        elevation_m=0,
    )


def test_fao56_et0_madison_reference_point():
    engine = SmartGardenerEngine()
    weather = parse_weather({
        **_weather(15, temp_max=26.6, temp_min=14.8, humidity=61),
        "date": "2026-07-15",
        "solar_radiation": 19.0,
        "wind_speed_2m": 1.2,
    })

    assert engine.calculate_et0(weather, latitude_deg=43.07, elevation_m=264) == pytest.approx(3.88, rel=0.03)


def test_fao56_et0_bangkok_tropical_reference():
    engine = SmartGardenerEngine()
    weather = parse_weather({
        "date": "2026-04-15",
        "temp_max": 34.8,
        "temp_min": 25.6,
        "temp_avg": 30.2,
        "humidity_avg": 63,
        "humidity_max": 85,
        "wind_speed_2m": 2.0,
        "solar_radiation": 22.65,
        "precipitation": 0,
    })

    et0 = engine.calculate_et0(weather, latitude_deg=13.73, elevation_m=2)

    assert 5.4 < et0 < 6.2, f"Bangkok tropical ET0 out of envelope: {et0}"
    assert et0 == pytest.approx(5.71, rel=0.05)


def test_fao56_et0_la_paz_high_altitude_reference():
    engine = SmartGardenerEngine()
    weather = parse_weather({
        "date": "2026-08-15",
        "temp_max": 17.0,
        "temp_min": 1.0,
        "temp_avg": 9.0,
        "humidity_avg": 50,
        "humidity_max": 75,
        "wind_speed_2m": 1.5,
        "solar_radiation": 18.0,
        "precipitation": 0,
    })

    et0 = engine.calculate_et0(weather, latitude_deg=-16.5, elevation_m=3640)

    assert 2.8 < et0 < 5.0, f"La Paz altitude ET0 out of envelope: {et0}"


def test_fao56_psychrometric_constant_scales_with_elevation():
    assert _psychrometric_constant(0) == pytest.approx(0.0673, abs=0.0005)
    assert _psychrometric_constant(1500) == pytest.approx(0.0563, abs=0.0005)
    assert _psychrometric_constant(3000) == pytest.approx(0.0473, abs=0.0010)


def test_fao56_extraterrestrial_radiation_southern_hemisphere():
    ra_north_summer = _extraterrestrial_radiation(16.5, 227)
    ra_south_winter = _extraterrestrial_radiation(-16.5, 227)

    assert ra_north_summer > ra_south_winter
    assert ra_north_summer - ra_south_winter > 5


def _disease_test_profile(disease: str):
    susceptibility_key = f"sus_{disease}"
    return crop_profile_from_backend(
        "Test crop",
        "Vegetables",
        {
            **PROFILE,
            "sus_powdery_mildew": 0.2,
            "sus_alternaria": 0.2,
            "sus_rust": 0.2,
            susceptibility_key: 0.2,
        },
    )


def _disease_test_plant(observed_at: datetime | None = None):
    engine = SmartGardenerEngine()
    plant = engine._parse_grid_cells(
        [{"col": 1, "row": 1, "plant_type": "Test crop", "planted_date": "2026-04-01"}],
        date(2026, 4, 20),
    )[0]
    plant.last_disease_observed_at = observed_at
    return plant


def _disease_risk_for(disease: str, observed_at: datetime | None, weather_kwargs: dict, phase=GrowthPhase.MID_SEASON):
    engine = SmartGardenerEngine()
    profile = _disease_test_profile(disease)
    plant = _disease_test_plant(observed_at)
    history = [parse_weather(_weather(day, **weather_kwargs)) for day in range(13, 20)]
    today = parse_weather(_weather(20, **weather_kwargs))
    forecast = [parse_weather(_weather(day, **weather_kwargs)) for day in range(21, 24)]

    risks = engine._assess_disease_risks(
        profile,
        today,
        forecast,
        history,
        age_days=plant.age_days,
        phase=phase,
        soil=get_soil_profile("loam"),
        plant=plant,
    )
    return next(risk for risk in risks if risk.disease == disease)


def test_inoculum_carryover_applies_to_powdery_mildew():
    weather = {"rain": 0, "humidity": 60, "temp_max": 24, "temp_min": 18}

    baseline = _disease_risk_for("powdery_mildew", None, weather)
    with_inoculum = _disease_risk_for("powdery_mildew", datetime(2026, 4, 13), weather)

    assert 0.09 <= with_inoculum.risk_level - baseline.risk_level <= 0.13


def test_inoculum_carryover_applies_to_alternaria():
    weather = {"rain": 4, "humidity": 88, "temp_max": 28, "temp_min": 22}

    baseline = _disease_risk_for("alternaria", None, weather)
    with_inoculum = _disease_risk_for("alternaria", datetime(2026, 4, 13), weather)

    assert with_inoculum.risk_level > baseline.risk_level


def test_inoculum_carryover_applies_to_rust():
    weather = {"rain": 1, "humidity": 88, "temp_max": 22, "temp_min": 16}

    baseline = _disease_risk_for("rust", None, weather, phase=GrowthPhase.DEVELOPMENT)
    with_inoculum = _disease_risk_for("rust", datetime(2026, 4, 13), weather, phase=GrowthPhase.DEVELOPMENT)

    assert 0.07 <= with_inoculum.risk_level - baseline.risk_level <= 0.11


def test_fusarium_risk_model_triggers_in_warm_wet_root_stress():
    weather = {"rain": 5, "humidity": 82, "temp_max": 30, "temp_min": 22}

    risk = _disease_risk_for(
        "fusarium",
        datetime(2026, 4, 13),
        weather,
        phase=GrowthPhase.MID_SEASON,
    )

    assert risk.disease == "fusarium"
    assert risk.is_significant
    assert "тепла волога" in risk.description
    assert "сівозміну" in risk.recommendation


def test_fusarium_uses_soil_biocontrol_protection_profile():
    recommendation = recommend_protection("fusarium", 0.75)

    assert recommendation.profile.id == "fusarium_soil_biocontrol"
    assert "fusarium" in recommendation.profile.target_diseases
    assert recommendation.profile.pre_harvest_interval_days == 0


def test_inoculum_pressure_decay_curve():
    engine = SmartGardenerEngine()
    plant = _disease_test_plant()
    today = date(2026, 6, 1)

    plant.last_disease_observed_at = datetime(2026, 5, 25)
    assert engine._inoculum_pressure(plant, today) == 1.0
    plant.last_disease_observed_at = datetime(2026, 5, 12)
    assert engine._inoculum_pressure(plant, today) == 0.65
    plant.last_disease_observed_at = datetime(2026, 4, 22)
    assert engine._inoculum_pressure(plant, today) == 0.35
    plant.last_disease_observed_at = datetime(2026, 4, 10)
    assert engine._inoculum_pressure(plant, today) == 0.0


def test_inoculum_carryover_default_zero_if_never_observed():
    engine = SmartGardenerEngine()
    plant = _disease_test_plant()

    assert engine._inoculum_pressure(plant, date(2026, 6, 1)) == 0.0


def test_watering_task_exposes_confidence_and_trigger_factors():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-03-01", "category": "Овочі"}],
        {"Томат": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=35, temp_max=34, temp_min=20),
        weather_history=[
            _weather(i, rain=0, humidity=35, temp_max=34, temp_min=20)
            for i in range(1, 20)
        ],
        weather_forecast=[_weather(21, rain=0, humidity=40, temp_max=30, temp_min=18)],
        soil_type="sand",
    )

    watering = next(t for t in tasks if t["task_type"] == "watering")
    assert watering["confidence"] >= 80
    assert any("Полив: дефіцит" in reason for reason in watering["reasons"])
    assert any("Ґрунт: Піщаний" in reason for reason in watering["reasons"])


def test_profile_confidence_caps_task_confidence():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-03-01", "category": "Овочі"}],
        {"Томат": {**PROFILE, "profile_confidence": 55, "validation_warnings": ["kc_mid clamped"]}},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=35, temp_max=34, temp_min=20),
        weather_history=[
            _weather(i, rain=0, humidity=35, temp_max=34, temp_min=20)
            for i in range(1, 20)
        ],
        weather_forecast=[_weather(21, rain=0, humidity=40, temp_max=30, temp_min=18)],
        soil_type="sand",
    )

    watering = next(t for t in tasks if t["task_type"] == "watering")
    assert 70 < watering["confidence"] < 92
    assert any("Довіра до профілю культури: 55%" in reason for reason in watering["reasons"])


def test_fertilizing_uses_weather_window_and_leaching_factors():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-03-01", "category": "Овочі"}],
        {"Томат": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=65, temp_max=24, temp_min=15),
        weather_history=[
            _weather(i, rain=20 if i >= 16 else 0, humidity=85, temp_max=22, temp_min=14)
            for i in range(1, 20)
        ],
        weather_forecast=[_weather(21, rain=0), _weather(22, rain=0), _weather(23, rain=0)],
        soil_type="loam",
    )

    feeding = next(t for t in tasks if t["task_type"] == "fertilizing")
    assert feeding["confidence"] >= 90
    assert any("Ризик вимивання" in reason for reason in feeding["reasons"])
    assert any("Вікно внесення" in reason for reason in feeding["reasons"])


def test_fungicide_protection_uses_forecast_and_explains_factors():
    profile = {
        **PROFILE,
        "sus_late_blight": 0.95,
        "treatment_guide": {
            "biological_controls": ["Bacillus subtilis / Trichoderma — Фітоспорин, Триходермін або аналоги."],
            "chemical_controls": ["Манкоцеб або металаксил-М + манкоцеб — Ридоміл Голд, Акробат або аналоги за етикеткою."],
        },
    }
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-03-01", "category": "Овочі"}],
        {"Томат": profile},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=2, humidity=88, temp_max=22, temp_min=14),
        weather_history=[
            _weather(i, rain=2, humidity=86, temp_max=22, temp_min=14)
            for i in range(13, 20)
        ],
        weather_forecast=[
            _weather(21, rain=3, humidity=90, temp_max=21, temp_min=13),
            _weather(22, rain=2, humidity=88, temp_max=20, temp_min=12),
            _weather(23, rain=0, humidity=82, temp_max=22, temp_min=14),
        ],
        soil_type="clay",
    )

    protection = next(t for t in tasks if t["task_type"] == "disease_protection")
    assert protection["confidence"] >= 80
    assert protection["title"].startswith("Фунгіцидний захист")
    assert protection["reason_groups"].get("weather")
    protection_text = " ".join(protection["reason_groups"].get("protection", []))
    assert "Біологічні:" in protection_text
    assert "Хімічні:" in protection_text


def test_ipm_pest_protection_uses_common_pests_profile():
    profile = {
        **PROFILE,
        "common_pests": [
            {
                "name": "Попелиця",
                "likelihood": "high",
                "symptoms": "скручене липке листя, колонії на молодих пагонах",
                "treatment": "Огляд молодих пагонів, змивання водою або біоінсектицид; інсектицид тільки при масовому заселенні.",
            }
        ],
        "treatment_guide": {
            "pest_controls": ["Попелиця: перевірити нижній бік листка і молоді пагони, почати з м'яких IPM-заходів."],
            "biological_controls": ["Bacillus thuringiensis або ентомофаги — біоінсектицид/корисні комахи за етикеткою."],
            "chemical_controls": ["Ацетаміприд або спіротетрамат — Моспілан, Мовенто або аналоги за діючою речовиною."],
        },
    }

    result = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "РўРѕРјР°С‚", "planted_date": "2026-03-01", "category": "РћРІРѕС‡С–"}],
        {"РўРѕРјР°С‚": profile},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=62, temp_max=24, temp_min=15),
        weather_history=[_weather(i, rain=0, humidity=60, temp_max=24, temp_min=15) for i in range(15, 20)],
        weather_forecast=[_weather(21, rain=0, humidity=60, temp_max=24, temp_min=15)],
        soil_type="loam",
    )

    pest_tasks = [task for task in result["tasks"] if task["task_type"] == "pest_control"]
    assert pest_tasks
    assert pest_tasks[0]["recommendation_type"] == "ipm_insecticide_intervention"
    assert "Попелиця" in pest_tasks[0]["title"]
    assert pest_tasks[0]["reason_groups"].get("protection")
    protection_text = " ".join(pest_tasks[0]["reason_groups"]["protection"])
    assert "Біологічні:" in protection_text
    assert "Хімічні:" in protection_text


def test_soil_pests_do_not_use_leaf_inspection_template():
    profile = {
        **PROFILE,
        "common_pests": [
            {
                "name": "Дротяник",
                "likelihood": "high",
                "symptoms": "пошкоджені корені, ходи в бульбах, рослина в'яне без листкових плям",
                "treatment": "Перевірити ґрунт і кореневу зону, використати приманкові пастки; інсектицид лише після підтвердження.",
            }
        ],
    }

    result = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "Картопля", "planted_date": "2026-04-01", "category": "Овочі"}],
        {"Картопля": profile},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=1, humidity=68, temp_max=23, temp_min=14),
        weather_history=[_weather(i, rain=1, humidity=68, temp_max=23, temp_min=14) for i in range(15, 20)],
        weather_forecast=[_weather(21, rain=1, humidity=68, temp_max=24, temp_min=15)],
        soil_type="loam",
    )

    pest_task = next(task for task in result["tasks"] if task["task_type"] == "pest_control")
    text = " ".join([
        pest_task["description"],
        *pest_task["constraints"],
    ]).lower()

    assert "дротяник" in pest_task["title"].lower()
    assert "ґрунт" in text
    assert "корен" in text
    assert "10-20 лист" not in text
    assert "нижній бік лист" not in text


def test_ipm_pest_protection_is_hidden_during_hot_spray_window():
    profile = {
        **PROFILE,
        "common_pests": [
            {
                "name": "Павутинний кліщ",
                "likelihood": "high",
                "symptoms": "жовті крапки на листі, тонка павутинка",
                "treatment": "Підвищити вологість, змити колонії, за потреби застосувати дозволений акарицид ввечері.",
            }
        ],
    }

    result = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "РўРѕРјР°С‚", "planted_date": "2026-03-01", "category": "РћРІРѕС‡С–"}],
        {"РўРѕРјР°С‚": profile},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=42, temp_max=32, temp_min=20),
        weather_history=[_weather(i, rain=0, humidity=42, temp_max=31, temp_min=20) for i in range(15, 20)],
        weather_forecast=[_weather(21, rain=0, humidity=40, temp_max=33, temp_min=20)],
        soil_type="loam",
        manual_observations=[
            {
                "scope": "plot",
                "symptoms": ["павутинний кліщ", "павутинка на листі"],
                "observed_at": "2026-04-20T08:00:00+00:00",
            }
        ],
    )

    hidden = [task for task in result["hidden_tasks"] if task["task_type"] == "pest_control"]
    assert hidden
    assert "відкласти" in hidden[0]["title"]
    assert "спека" in " ".join(hidden[0]["constraints"])
    assert hidden[0]["blocked_reasons"]


def test_engine_handles_empty_weather_context_without_crashing():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-04-01", "category": "Овочі"}],
        {"Томат": PROFILE},
        today=date(2026, 4, 20),
        weather_today=None,
        weather_forecast=[],
        weather_history=[],
        soil_type="loam",
    )

    assert tasks
    assert all("task_type" in task for task in tasks)


def test_late_blight_requires_sustained_leaf_wetness():
    dry_leaf_weather = {
        **_weather(20, rain=0, humidity=76, temp_max=21, temp_min=13),
        "humidity_max": 86,
        "cloud_cover": 80,
        "has_dew": False,
        "is_fog": False,
    }

    result = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "РўРѕРјР°С‚", "planted_date": "2026-03-01", "category": "РћРІРѕС‡С–"}],
        {"РўРѕРјР°С‚": {**PROFILE, "sus_late_blight": 0.95}},
        today=date(2026, 4, 20),
        weather_today=dry_leaf_weather,
        weather_history=[{**dry_leaf_weather, "date": f"2026-04-{day:02d}"} for day in range(13, 20)],
        weather_forecast=[{**dry_leaf_weather, "date": f"2026-04-{day:02d}"} for day in range(21, 24)],
        soil_type="loam",
    )

    disease_items = [item for item in result["tasks"] + result["hidden_tasks"] if item["task_type"] == "disease_protection"]
    reasons = " ".join(reason for item in disease_items for reason in item["reasons"])
    assert "NegFry" not in reasons
    assert "Smith Periods" not in reasons


def test_late_blight_uses_negfry_and_smith_periods():
    wet_weather = {
        **_weather(20, rain=3, humidity=91, temp_max=21, temp_min=13),
        "humidity_max": 96,
        "cloud_cover": 90,
        "has_dew": True,
        "is_fog": False,
    }

    result = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "РўРѕРјР°С‚", "planted_date": "2026-03-01", "category": "РћРІРѕС‡С–"}],
        {"РўРѕРјР°С‚": {**PROFILE, "sus_late_blight": 0.95}},
        today=date(2026, 4, 20),
        weather_today=wet_weather,
        weather_history=[{**wet_weather, "date": f"2026-04-{day:02d}"} for day in range(13, 20)],
        weather_forecast=[{**wet_weather, "date": f"2026-04-{day:02d}"} for day in range(21, 24)],
        soil_type="loam",
    )

    disease_items = [item for item in result["tasks"] + result["hidden_tasks"] if item["task_type"] == "disease_protection"]
    assert disease_items
    reasons = " ".join(reason for item in disease_items for reason in item["reasons"])
    assert "NegFry" in reasons
    assert "Smith Periods" in reasons


def test_protection_catalog_has_commercial_profile_depth():
    assert len(PROTECTION_PROFILES) >= 12
    for profile_id in ["contact_copper", "mancozeb_contact", "azoxystrobin_qoi", "propiconazole_dmi", "bacillus_biocontrol"]:
        assert profile_id in PROTECTION_PROFILES

    assert recommend_protection("late_blight", 0.8).profile.id == "systemic_oomycete"
    assert recommend_protection("powdery_mildew", 0.8).profile.id == "azoxystrobin_qoi"
    assert recommend_protection("powdery_mildew", 0.8, crop_name="Apple", crop_category="Fruit trees").profile.id != "azoxystrobin_qoi"
    assert recommend_protection("alternaria", 0.8, crop_name="Apple", crop_category="Fruit trees").profile.id != "azoxystrobin_qoi"


def test_ipm_pest_protection_filters_out_fungicide_guidance():
    profile = {
        **PROFILE,
        "common_pests": [
            {
                "name": "Aphid",
                "likelihood": "high",
                "symptoms": "sticky curled leaves and colonies on young shoots",
                "treatment": "Confirm colonies first; use insecticidal soap, beneficial insects, or acetamiprid only after threshold.",
            }
        ],
        "treatment_guide": {
            "pest_controls": ["Aphid: inspect young shoots and underside of leaves."],
            "biological_controls": [
                "Bacillus subtilis fungicide for leaf disease",
                "Beneficial insects against aphids",
            ],
            "chemical_controls": [
                "Mancozeb fungicide for late blight",
                "Acetamiprid insecticide for aphids",
            ],
        },
    }

    result = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "Tomato", "planted_date": "2026-03-01", "category": "Vegetables"}],
        {"Tomato": profile},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=62, temp_max=24, temp_min=15),
        weather_history=[_weather(i, rain=0, humidity=60, temp_max=24, temp_min=15) for i in range(15, 20)],
        weather_forecast=[_weather(21, rain=0, humidity=60, temp_max=24, temp_min=15)],
        soil_type="loam",
    )

    pest_task = next(task for task in result["tasks"] if task["task_type"] == "pest_control")
    protection_text = " ".join(pest_task["reason_groups"]["protection"])
    assert "Acetamiprid insecticide" in protection_text
    assert "Mancozeb fungicide" not in protection_text
    assert "Bacillus subtilis fungicide" not in protection_text


def test_fungicide_protection_filters_out_insecticide_guidance():
    profile = {
        **PROFILE,
        "sus_late_blight": 0.95,
        "common_diseases": [
            {
                "name": "Late blight",
                "likelihood": "high",
                "symptoms": ["wet dark leaf spots"],
                "treatment": ["Use mancozeb fungicide or metalaxyl-M mixture according to label."],
            }
        ],
        "treatment_guide": {
            "biological_controls": ["Bacillus subtilis fungicide for leaf disease"],
            "chemical_controls": [
                "Acetamiprid insecticide for aphids",
                "Mancozeb fungicide for late blight",
            ],
        },
    }

    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Tomato", "planted_date": "2026-03-01", "category": "Vegetables"}],
        {"Tomato": profile},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=2, humidity=88, temp_max=22, temp_min=14),
        weather_history=[_weather(i, rain=2, humidity=86, temp_max=22, temp_min=14) for i in range(13, 20)],
        weather_forecast=[
            _weather(21, rain=3, humidity=90, temp_max=21, temp_min=13),
            _weather(22, rain=2, humidity=88, temp_max=20, temp_min=12),
            _weather(23, rain=0, humidity=82, temp_max=22, temp_min=14),
        ],
        soil_type="clay",
    )

    protection = next(task for task in tasks if task["task_type"] == "disease_protection")
    protection_text = " ".join(protection["reason_groups"]["protection"])
    assert "Mancozeb fungicide" in protection_text
    assert "Acetamiprid insecticide" not in protection_text


def test_initial_soil_fertility_can_cover_start_fertilizing_need():
    rich_profile = {**PROFILE, "phosphorus": 1.0, "initial_days": 20}
    cells = [{"col": 1, "row": 2, "plant_type": "Watermelon", "planted_date": "2026-04-10", "category": "Vegetables"}]
    common = {
        "today": date(2026, 4, 20),
        "weather_today": _weather(20, rain=0, humidity=55, temp_max=24, temp_min=14),
        "weather_history": [_weather(day, rain=0, humidity=55, temp_max=24, temp_min=14) for day in range(1, 20)],
        "weather_forecast": [_weather(21, rain=0), _weather(22, rain=0), _weather(23, rain=0)],
    }

    sand_tasks = generate_tasks(
        cells,
        {"Watermelon": rich_profile},
        soil_type="sand",
        **common,
    )
    chernozem_tasks = generate_tasks(
        cells,
        {"Watermelon": rich_profile},
        soil_type="chernozem",
        **common,
    )

    assert any(task["task_type"] == "fertilizing" for task in sand_tasks)
    assert not any(task["task_type"] == "fertilizing" for task in chernozem_tasks)


def test_nutrient_pool_reports_ph_and_antagonism_factors():
    engine = SmartGardenerEngine()
    soil = get_soil_profile("clay")
    plant = engine._parse_grid_cells(
        [{"col": 1, "row": 2, "plant_type": "Watermelon", "planted_date": "2026-04-01"}],
        date(2026, 4, 20),
    )[0]
    plant.k_applied_season_g_m2 = 30
    plant.ca_applied_season_g_m2 = 80

    lines = engine._nutrient_ledger_lines(plant, soil, None)

    assert any("Стартовий пул" in line for line in lines)
    assert any("Доступність P" in line for line in lines)
    assert any("Антагонізм" in line for line in lines)


def test_watering_hidden_when_tomorrow_rain_and_deficit_not_critical():
    analysis = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-04-16", "category": "Овочі"}],
        {"Томат": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=60, temp_max=23, temp_min=14),
        weather_history=[_weather(i, rain=0, humidity=60, temp_max=23, temp_min=14) for i in range(14, 20)],
        weather_forecast=[_weather(21, rain=8, humidity=88, temp_max=20, temp_min=13)],
        soil_type="loam",
    )

    assert not any(t["task_type"] == "watering" for t in analysis["tasks"])
    hidden = next(t for t in analysis["hidden_tasks"] if t["task_type"] == "watering")
    assert hidden["is_hidden"] is True
    assert hidden["blocked_reasons"]


def test_fungicide_hidden_before_harvest_interval():
    analysis = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-02-15", "category": "Овочі"}],
        {"Томат": {**PROFILE, "days_to_harvest_min": 68, "days_to_harvest_max": 90, "sus_late_blight": 0.95}},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=2, humidity=88, temp_max=22, temp_min=14),
        weather_history=[_weather(i, rain=2, humidity=86, temp_max=22, temp_min=14) for i in range(13, 20)],
        weather_forecast=[
            _weather(21, rain=3, humidity=90, temp_max=21, temp_min=13),
            _weather(22, rain=2, humidity=88, temp_max=20, temp_min=12),
        ],
        soil_type="clay",
    )

    assert not any(t["task_type"] == "disease_protection" for t in analysis["tasks"])
    hidden = next(t for t in analysis["hidden_tasks"] if t["task_type"] == "disease_protection")
    assert hidden["recommendation_type"] in {"контактний фунгіцид", "системний фунгіцид"}
    assert any("pre-harvest interval" in item for item in hidden["constraints"])


def test_young_tomato_preventive_fungicide_waits_for_adaptation():
    analysis = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "\u0422\u043e\u043c\u0430\u0442", "planted_date": "2026-04-18", "category": "\u041e\u0432\u043e\u0447\u0456"}],
        {"\u0422\u043e\u043c\u0430\u0442": {**PROFILE, "sus_late_blight": 0.95}},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=2, humidity=88, temp_max=22, temp_min=14),
        weather_history=[_weather(i, rain=2, humidity=88, temp_max=22, temp_min=14) for i in range(13, 20)],
        weather_forecast=[
            _weather(21, rain=3, humidity=90, temp_max=21, temp_min=13),
            _weather(22, rain=2, humidity=88, temp_max=20, temp_min=12),
        ],
        soil_type="clay",
    )

    assert not any(t["task_type"] == "disease_protection" for t in analysis["tasks"])
    hidden = next(t for t in analysis["hidden_tasks"] if t["task_type"] == "disease_protection")
    assert hidden["is_hidden"] is True
    assert any("адаптації" in reason for reason in hidden["blocked_reasons"])


def test_biofungicide_is_allowed_immediately_after_transplanting():
    engine = SmartGardenerEngine()
    plant = engine._parse_grid_cells(
        [{"col": 1, "row": 2, "plant_type": "\u0422\u043e\u043c\u0430\u0442", "planted_date": "2026-04-19"}],
        date(2026, 4, 20),
    )[0]
    plant.last_disease_observed_at = datetime(2026, 4, 20)
    profile = crop_profile_from_backend("\u0422\u043e\u043c\u0430\u0442", "\u041e\u0432\u043e\u0447\u0456", PROFILE)
    product = recommend_protection("observed_symptoms", 0.4).profile

    assert product.id == "bacillus_biocontrol"
    assert SmartGardenerEngine._disease_timing_blockers(plant, product, profile, date(2026, 4, 20)) == []


WATERMELON_PROFILE = {
    **PROFILE,
    "emoji": "🍉",
    "t_min_growth": 12,
    "t_optimal_min": 20,
    "frost_tolerance": 2,
    "days_to_harvest_min": 80,
    "days_to_harvest_max": 110,
}


def test_cold_stress_detects_forecast_cooling_before_frost():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Watermelon", "planted_date": "2026-04-10", "category": "Овочі"}],
        {"Watermelon": WATERMELON_PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, temp_max=19, temp_min=12),
        weather_forecast=[
            _weather(21, temp_max=17, temp_min=10),
            _weather(22, temp_max=16, temp_min=9),
            _weather(23, temp_max=18, temp_min=11),
        ],
        soil_type="loam",
    )

    cold = next(t for t in tasks if t["task_type"] == "cold_stress")
    assert cold["priority"] in {"high", "critical"}
    assert cold["due_date"] == "2026-04-21"
    assert any("Поріг росту культури: 12°C" in reason for reason in cold["reasons"])


def test_cold_stress_boosts_priority_for_young_warm_season_crop():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Watermelon", "planted_date": "2026-04-15", "category": "Овочі"}],
        {"Watermelon": WATERMELON_PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, temp_max=18, temp_min=11),
        weather_forecast=[_weather(21, temp_max=16, temp_min=10, rain=3, humidity=90)],
        soil_type="loam",
    )

    cold = next(t for t in tasks if t["task_type"] == "cold_stress")
    assert cold["priority"] in {"high", "critical"}
    assert cold["recommendation_type"] == "укриття / агроволокно"
    assert any("Молода рослина" in reason for reason in cold["reasons"])

def test_frost_protection_suppresses_duplicate_cold_stress_for_same_plant():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Watermelon", "planted_date": "2026-04-15", "category": "Овочі"}],
        {"Watermelon": WATERMELON_PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, temp_max=18, temp_min=10),
        weather_forecast=[
            _weather(21, temp_max=11, temp_min=1),
            _weather(22, temp_max=15, temp_min=8),
        ],
        soil_type="loam",
    )

    assert any(t["task_type"] == "frost_protection" for t in tasks)
    assert not any(t["task_type"] == "cold_stress" for t in tasks)


RASPBERRY_PROFILE = {
    **PROFILE,
    "emoji": "\U0001f347",
    "category": "\u042f\u0433\u0456\u0434\u043d\u0456 \u043a\u0443\u0449\u0456",
    "t_min_growth": 8,
    "t_optimal_min": 16,
    "frost_tolerance": -2,
}


def test_raspberry_positive_chill_does_not_trigger_cold_stress():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Raspberry", "planted_date": "2026-04-01", "category": "Berries"}],
        {"Raspberry": RASPBERRY_PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, temp_max=10, temp_min=2),
        weather_forecast=[
            _weather(21, temp_max=9, temp_min=2),
            _weather(22, temp_max=11, temp_min=3),
            _weather(23, temp_max=12, temp_min=4),
        ],
        soil_type="loam",
    )

    assert not any(t["task_type"] == "cold_stress" for t in tasks)


def test_raspberry_subzero_cooling_triggers_cold_stress():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Raspberry", "planted_date": "2026-04-01", "category": "Berries"}],
        {"Raspberry": RASPBERRY_PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, temp_max=10, temp_min=2),
        weather_forecast=[
            _weather(21, temp_max=8, temp_min=-1),
            _weather(22, temp_max=11, temp_min=3),
        ],
        soil_type="loam",
    )

    cold = next(t for t in tasks if t["task_type"] == "cold_stress")
    assert cold["due_date"] == "2026-04-21"


def _watering_liters(tasks: list[dict]) -> float:
    watering = next(t for t in tasks if t["task_type"] == "watering")
    return float(str(watering["amount"]).split()[0])


def test_water_balance_uses_soil_profile_not_crop_field_capacity():
    cells = [{"col": 1, "row": 2, "plant_type": "TestCrop", "planted_date": "2026-03-01"}]
    weather_history = [
        _weather(i, rain=0, humidity=35, temp_max=34, temp_min=20)
        for i in range(1, 20)
    ]
    base_profile = {
        **PROFILE,
        "root_depth_initial_cm": 20,
        "root_depth_max_cm": 90,
        "critical_depletion": 0.45,
    }

    low_crop_capacity = generate_tasks(
        cells,
        {"TestCrop": {**base_profile, "field_capacity_mm": 80, "wilting_point_mm": 20}},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=35, temp_max=34, temp_min=20),
        weather_history=weather_history,
        soil_type="loam",
    )
    high_crop_capacity = generate_tasks(
        cells,
        {"TestCrop": {**base_profile, "field_capacity_mm": 1000, "wilting_point_mm": 50}},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=35, temp_max=34, temp_min=20),
        weather_history=weather_history,
        soil_type="loam",
    )

    assert _watering_liters(low_crop_capacity) == _watering_liters(high_crop_capacity)


def test_water_balance_changes_by_soil_type():
    cells = [{"col": 1, "row": 2, "plant_type": "TestCrop", "planted_date": "2026-03-01"}]
    weather_history = [
        _weather(i, rain=0, humidity=35, temp_max=34, temp_min=20)
        for i in range(1, 20)
    ]
    profile = {
        **PROFILE,
        "root_depth_initial_cm": 20,
        "root_depth_max_cm": 90,
        "critical_depletion": 0.45,
    }

    sand_tasks = generate_tasks(
        cells,
        {"TestCrop": profile},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=35, temp_max=34, temp_min=20),
        weather_history=weather_history,
        soil_type="sand",
    )
    chernozem_tasks = generate_tasks(
        cells,
        {"TestCrop": profile},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=35, temp_max=34, temp_min=20),
        weather_history=weather_history,
        soil_type="chernozem",
    )

    assert _watering_liters(chernozem_tasks) > _watering_liters(sand_tasks)


def test_soil_profile_exposes_agronomic_properties():
    sand = get_soil_profile("sand")
    chernozem = get_soil_profile("chernozem")

    assert sand.available_water_mm_per_m < chernozem.available_water_mm_per_m
    assert sand.nitrogen_leaching_multiplier > chernozem.nitrogen_leaching_multiplier
    assert chernozem.nutrient_retention > sand.nutrient_retention
    assert sand.to_dict()["ph_label"]


def test_nutrient_leaching_uses_soil_profile():
    engine = SmartGardenerEngine()
    rainy_history = [
        parse_weather(_weather(i, rain=18, humidity=85, temp_max=22, temp_min=14))
        for i in range(15, 20)
    ]

    sand_risk = engine._assess_nutrient_leaching(rainy_history, get_soil_profile("sand"))
    chernozem_risk = engine._assess_nutrient_leaching(rainy_history, get_soil_profile("chernozem"))

    assert sand_risk > chernozem_risk


def test_fertilizer_profile_recommendation_uses_soil_context():
    sand = get_soil_profile("sand")
    recommendation = recommend_fertilizer(
        "vegetative_growth",
        sand,
        nitrogen_g_m2=3.0,
        phosphorus_g_m2=1.0,
        potassium_g_m2=1.0,
    )

    assert recommendation.profile == get_fertilizer_profile("nitrogen_growth")
    assert recommendation.recommendation_type
    assert "N 3.0" in recommendation.amount
    assert any("азот" in reason.lower() for reason in recommendation.reasons)


def test_fertilizing_task_contains_fertilizer_reason_group():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "TestCrop", "planted_date": "2026-04-01"}],
        {"TestCrop": PROFILE},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=0, humidity=65, temp_max=24, temp_min=15),
        weather_history=[_weather(i, rain=0, humidity=65, temp_max=24, temp_min=15) for i in range(1, 20)],
        weather_forecast=[_weather(21, rain=0), _weather(22, rain=0), _weather(23, rain=0)],
        soil_type="sand",
    )

    feeding = next(t for t in tasks if t["task_type"] == "fertilizing")
    assert feeding["recommendation_type"]
    assert feeding["reason_groups"].get("fertilizer")


def test_protection_profile_recommendation_uses_disease_and_risk():
    low = recommend_protection("late_blight", 0.45)
    high = recommend_protection("late_blight", 0.85)
    mildew = recommend_protection("powdery_mildew", 0.55)
    apple = recommend_protection("late_blight", 0.85, crop_name="Яблуня", crop_category="Плодові")

    assert low.profile.frac_group == "M01"
    assert high.profile.protection_type == "системний фунгіцид"
    assert high.profile.pre_harvest_interval_days > low.profile.pre_harvest_interval_days
    assert mildew.profile.id == "sulfur_contact"
    assert apple.profile.id == "tree_phytophthora_phosphonate"


def test_apple_phytophthora_uses_tree_root_crown_rot_model():
    apple_profile = {
        **PROFILE,
        "category": "Плодові",
        "sus_late_blight": 0.9,
        "common_diseases": [
            {
                "name": "фітофторозна гниль кореневої шийки/коренів",
                "type": "oomycete",
                "likelihood": "high",
                "symptoms": ["темна кора біля кореневої шийки", "слабкий ріст"],
                "risk_conditions": ["застій води", "важкий ґрунт"],
                "treatment": ["дренаж", "фосфіти або фосетил-Al за етикеткою"],
            }
        ],
    }

    result = generate_analysis(
        [{"col": 1, "row": 2, "plant_type": "Яблуня", "planted_date": "2024-03-01", "category": "Плодові"}],
        {"Яблуня": apple_profile},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=12, humidity=90, temp_max=18, temp_min=9),
        weather_history=[_weather(i, rain=8, humidity=88, temp_max=17, temp_min=8) for i in range(13, 20)],
        weather_forecast=[
            _weather(21, rain=6, humidity=88, temp_max=18, temp_min=9),
            _weather(22, rain=4, humidity=86, temp_max=19, temp_min=10),
            _weather(23, rain=0, humidity=72, temp_max=20, temp_min=11),
        ],
        soil_type="clay",
    )

    protection = next(t for t in result["tasks"] + result["hidden_tasks"] if t["task_type"] == "disease_protection")
    text = " ".join([protection["title"], protection["description"], *protection["reasons"], *protection["constraints"]])
    assert "коренев" in text.lower()
    assert "фосф" in text.lower()
    assert "мідь" in text.lower()
    assert "NegFry" not in text
    assert "Smith Periods" not in text


def test_disease_task_contains_protection_profile_metadata():
    tasks = generate_tasks(
        [{"col": 1, "row": 2, "plant_type": "Томат", "planted_date": "2026-03-01", "category": "Овочі"}],
        {"Томат": {**PROFILE, "sus_late_blight": 0.95}},
        today=date(2026, 4, 20),
        weather_today=_weather(20, rain=2, humidity=88, temp_max=22, temp_min=14),
        weather_history=[_weather(i, rain=2, humidity=86, temp_max=22, temp_min=14) for i in range(13, 20)],
        weather_forecast=[
            _weather(21, rain=3, humidity=90, temp_max=21, temp_min=13),
            _weather(22, rain=2, humidity=88, temp_max=20, temp_min=12),
            _weather(23, rain=0, humidity=82, temp_max=22, temp_min=14),
        ],
        soil_type="clay",
    )

    protection = next(t for t in tasks if t["task_type"] == "disease_protection")
    assert protection["reason_groups"].get("protection")
    assert any(item.startswith("FRAC ") for item in protection["constraints"])
    assert any("rainfastness" in item for item in protection["constraints"])
