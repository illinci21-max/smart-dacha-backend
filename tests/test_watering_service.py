"""
Unit tests — алгоритм поливу.
pytest tests/test_watering_service.py
"""
import pytest
from datetime import datetime, timezone, timedelta
from app.services.watering_service import calculate_watering_need, WateringDecision


def make_crop(water_need=300, drought_tolerance=3):
    return {"water_need_ml_per_day": water_need, "drought_tolerance": drought_tolerance}


def make_weather(temp_avg=20.0, precip=0.0, rain_prob=0.0):
    return {"temp_avg": temp_avg, "precipitation": precip, "rain_probability": rain_prob}


class TestWateringAlgorithm:
    def test_no_watering_when_rain_expected(self):
        """Не поливати якщо очікується дощ >5мм з ймовірністю >70%."""
        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(days=3),
            crop=make_crop(),
            weather_today=make_weather(temp_avg=22, precip=8.0, rain_prob=80.0),
            weather_tomorrow=None,
        )
        assert decision.should_water is False
        assert decision.skip_reason == "rain_expected_today"

    def test_critical_urgency_after_long_dry(self):
        """Критична терміновість після тривалого часу без поливу."""
        crop = make_crop(drought_tolerance=2)  # critical після 4 днів
        last_watered = datetime.now(timezone.utc) - timedelta(days=5)

        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=last_watered,
            crop=crop,
            weather_today=make_weather(temp_avg=30.0),
            weather_tomorrow=None,
        )
        assert decision.should_water is True
        assert decision.urgency == "critical"

    def test_temp_factor_increases_water_need(self):
        """Висока температура збільшує потребу у воді."""
        normal = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(days=2),
            crop=make_crop(water_need=300),
            weather_today=make_weather(temp_avg=20.0),
            weather_tomorrow=None,
        )
        hot = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(days=2),
            crop=make_crop(water_need=300),
            weather_today=make_weather(temp_avg=35.0),
            weather_tomorrow=None,
        )
        if hot.should_water and normal.should_water:
            assert hot.amount_ml > normal.amount_ml

    def test_no_watering_if_watered_today(self):
        """Не поливати якщо поливали сьогодні."""
        decision = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(hours=2),
            crop=make_crop(),
            weather_today=make_weather(),
            weather_tomorrow=None,
        )
        assert decision.should_water is False

    def test_drought_tolerant_plant_needs_less_water(self):
        """Посухостійка рослина потребує менше поливу."""
        sensitive = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(days=3),
            crop=make_crop(drought_tolerance=1),
            weather_today=make_weather(temp_avg=25.0),
            weather_tomorrow=None,
        )
        tolerant = calculate_watering_need(
            plant_id="test",
            last_watered_at=datetime.now(timezone.utc) - timedelta(days=3),
            crop=make_crop(drought_tolerance=5),
            weather_today=make_weather(temp_avg=25.0),
            weather_tomorrow=None,
        )
        if sensitive.should_water and tolerant.should_water:
            assert sensitive.amount_ml > tolerant.amount_ml


class TestSATService:
    def test_sat_delta_below_base_is_zero(self):
        """Нижче базової температури — дельта САТ = 0."""
        from app.services.sat_service import calculate_sat_delta
        assert calculate_sat_delta(temp_avg=8.0, t_base=10.0) == 0.0

    def test_sat_delta_above_base(self):
        from app.services.sat_service import calculate_sat_delta
        assert calculate_sat_delta(temp_avg=20.0, t_base=10.0) == 10.0

    def test_growth_stage_detection(self):
        from app.services.sat_service import determine_growth_stage
        stages = [
            {"name": "сходи", "sat_from": 0, "sat_to": 150},
            {"name": "вегетація", "sat_from": 150, "sat_to": 500},
            {"name": "цвітіння", "sat_from": 500, "sat_to": 900},
        ]
        assert determine_growth_stage(0, stages) == "сходи"
        assert determine_growth_stage(100, stages) == "сходи"
        assert determine_growth_stage(300, stages) == "вегетація"
        assert determine_growth_stage(700, stages) == "цвітіння"
