"""Tests — SAT Service logic."""
import pytest
from app.services.sat_service import calculate_sat_delta, determine_growth_stage

GROWTH_STAGES = [
    {"name": "Проростання", "sat_from": 0, "sat_to": 150},
    {"name": "Розсада", "sat_from": 150, "sat_to": 400},
    {"name": "Вегетація", "sat_from": 400, "sat_to": 800},
    {"name": "Цвітіння", "sat_from": 800, "sat_to": 1200},
    {"name": "Плодоношення", "sat_from": 1200, "sat_to": 9999},
]


def test_sat_delta_above_base():
    assert calculate_sat_delta(20.0, 10.0) == pytest.approx(10.0)


def test_sat_delta_uses_upper_cutoff_when_min_max_available():
    assert calculate_sat_delta(
        temp_avg=34.0,
        t_base=10.0,
        temp_min=24.0,
        temp_max=44.0,
        t_upper=30.0,
    ) == pytest.approx(17.0)


def test_sat_delta_at_base():
    assert calculate_sat_delta(10.0, 10.0) == pytest.approx(0.0)


def test_sat_delta_below_base():
    # Якщо температура нижча за базову — дельта = 0 (рослина не розвивається)
    assert calculate_sat_delta(5.0, 10.0) == pytest.approx(0.0)


def test_growth_stage_early():
    stage = determine_growth_stage(100.0, GROWTH_STAGES)
    assert stage == "Проростання"


def test_growth_stage_flowering():
    stage = determine_growth_stage(950.0, GROWTH_STAGES)
    assert stage == "Цвітіння"


def test_growth_stage_last_when_exceeded():
    stage = determine_growth_stage(5000.0, GROWTH_STAGES)
    assert stage == "Плодоношення"


def test_growth_stage_empty_stages():
    stage = determine_growth_stage(500.0, [])
    assert stage is None
