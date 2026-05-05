"""Tests for calendar-anchored GDD for perennial plants."""
from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from app.services.agro_math import (
    cumulative_gdd_calendar_year,
    cumulative_gdd_from_planting,
)
from app.services.sat_service import _compute_sat_perennial


@dataclass
class FakeWeather:
    date: date
    temp_min: float
    temp_max: float


@dataclass
class FakePlant:
    sat_accumulated: float = 0
    sat_last_updated_at: date | None = None
    planted_date: date | None = None
    lifecycle_type: str = "perennial_woody_deciduous"
    id: str = "plant-1"


@dataclass
class FakeProfile:
    t_base: float = 5
    t_max_growth: float | None = None


def _make_history(
    year: int,
    days: int = 120,
    temp_min: float = 8,
    temp_max: float = 20,
) -> list[FakeWeather]:
    """Generate synthetic daily weather from Jan 1 of `year`."""
    start = date(year, 1, 1)
    return [
        FakeWeather(date=start + timedelta(days=i), temp_min=temp_min, temp_max=temp_max)
        for i in range(days)
    ]


class TestCalendarYearGDD:
    def test_starts_from_jan1(self):
        history = _make_history(2026, days=30, temp_min=10, temp_max=18)
        gdd = cumulative_gdd_calendar_year(
            history,
            today=date(2026, 1, 30),
            t_base=5,
        )
        assert gdd == pytest.approx(270, rel=0.01)

    def test_ignores_previous_year(self):
        history = [
            FakeWeather(date=date(2025, 12, 15), temp_min=20, temp_max=30),
            FakeWeather(date=date(2026, 1, 5), temp_min=10, temp_max=20),
        ]
        gdd = cumulative_gdd_calendar_year(
            history,
            today=date(2026, 1, 5),
            t_base=5,
        )
        assert gdd == pytest.approx(10)

    def test_zero_when_today_is_jan1(self):
        history = [FakeWeather(date=date(2026, 1, 1), temp_min=10, temp_max=20)]
        gdd = cumulative_gdd_calendar_year(
            history,
            today=date(2026, 1, 1),
            t_base=5,
        )
        assert gdd == pytest.approx(10)

    def test_handles_iso_string_dates(self):
        @dataclass
        class StrWeather:
            date: str
            temp_min: float
            temp_max: float

        history = [
            StrWeather(date="2026-03-15T00:00:00", temp_min=10, temp_max=20),
        ]
        gdd = cumulative_gdd_calendar_year(
            history,
            today=date(2026, 3, 15),
            t_base=5,
        )
        assert gdd == pytest.approx(10)

    def test_apple_realistic_kyiv_through_april(self):
        history = []
        start = date(2026, 1, 1)
        for i in range(120):
            day = start + timedelta(days=i)
            if day.month <= 2:
                tmin, tmax = -3, 3
            elif day.month == 3:
                tmin, tmax = 3, 12
            else:
                tmin, tmax = 8, 18
            history.append(FakeWeather(date=day, temp_min=tmin, temp_max=tmax))

        gdd = cumulative_gdd_calendar_year(
            history,
            today=date(2026, 4, 30),
            t_base=5,
        )
        assert 80 < gdd < 350, f"Apple Kyiv GDD seems off: {gdd}"


class TestPlantingAnchoredGDD:
    def test_annual_starts_from_planting(self):
        history = _make_history(2026, days=60, temp_min=10, temp_max=20)
        gdd = cumulative_gdd_from_planting(
            history,
            planted_date=date(2026, 2, 1),
            today=date(2026, 2, 28),
            t_base=5,
        )
        assert gdd == pytest.approx(280, rel=0.05)

    def test_does_not_count_before_planting(self):
        history = _make_history(2026, days=60, temp_min=15, temp_max=25)
        gdd = cumulative_gdd_from_planting(
            history,
            planted_date=date(2026, 2, 15),
            today=date(2026, 2, 28),
            t_base=5,
        )
        assert 150 < gdd < 240


class TestUpperCutoff:
    def test_perennial_gdd_respects_upper_cutoff(self):
        history = _make_history(2026, days=10, temp_min=20, temp_max=40)
        gdd_no_cap = cumulative_gdd_calendar_year(
            history,
            today=date(2026, 1, 10),
            t_base=5,
        )
        gdd_cap = cumulative_gdd_calendar_year(
            history,
            today=date(2026, 1, 10),
            t_base=5,
            t_upper=30,
        )
        assert gdd_no_cap > gdd_cap
        assert gdd_cap == pytest.approx(200, rel=0.05)


class TestPerennialSatTopup:
    def test_perennial_sat_rebuilds_from_jan1_when_batch_is_previous_year(self):
        plant = FakePlant(sat_accumulated=999, sat_last_updated_at=date(2025, 12, 31))
        weather_cache = {
            date(2026, 1, 1): FakeWeather(date(2026, 1, 1), temp_min=10, temp_max=20),
            date(2026, 1, 2): FakeWeather(date(2026, 1, 2), temp_min=11, temp_max=21),
        }

        sat = _compute_sat_perennial(
            plant,
            FakeProfile(t_base=5),
            weather_cache,
            today=date(2026, 1, 2),
        )

        assert sat == pytest.approx(21)

    def test_perennial_sat_uses_current_year_baseline_plus_delta(self):
        plant = FakePlant(sat_accumulated=100, sat_last_updated_at=date(2026, 1, 5))
        weather_cache = {
            date(2026, 1, 6): FakeWeather(date(2026, 1, 6), temp_min=10, temp_max=20),
            date(2026, 1, 7): FakeWeather(date(2026, 1, 7), temp_min=11, temp_max=21),
        }

        sat = _compute_sat_perennial(
            plant,
            FakeProfile(t_base=5),
            weather_cache,
            today=date(2026, 1, 7),
        )

        assert sat == pytest.approx(121)
