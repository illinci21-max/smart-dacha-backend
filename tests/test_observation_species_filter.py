"""Tests for species_filter and observed_perennial_season overrides."""
from datetime import date, timedelta

from app.services.lifecycle_types import LifecycleType, PerennialSeason
from app.services.smart_gardener_engine import PlantInstance, SmartGardenerEngine


def _make_plant(
    species: str = "Яблуня",
    category: str = "Дерева",
    age_years: int = 4,
    col: int = 0,
    row: int = 0,
) -> PlantInstance:
    return PlantInstance(
        cell_col=col,
        cell_row=row,
        plant_type=species,
        category=category,
        planted_date=f"{2026 - age_years}-04-01",
        lifecycle_type=LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
        age_years=age_years,
    )


class TestSpeciesFilterMatch:
    def test_observation_for_apple_matches_apple_plant(self):
        engine = SmartGardenerEngine()
        plant = _make_plant(species="Яблуня")
        today = date(2026, 4, 20)

        observations = [{
            "scope": "category",
            "species_filter": ["Яблуня"],
            "observed_perennial_season": "flowering_fruit_set",
            "observed_at": (today - timedelta(days=2)).isoformat(),
        }]

        season, source = engine._resolve_perennial_season(plant, today, observations)
        assert season == PerennialSeason.FLOWERING_FRUIT_SET
        assert "user-observation" in source

    def test_observation_for_pear_does_not_apply_to_apple(self):
        engine = SmartGardenerEngine()
        apple = _make_plant(species="Яблуня")
        today = date(2026, 4, 20)

        observations = [{
            "scope": "category",
            "species_filter": ["Груша"],
            "observed_perennial_season": "flowering_fruit_set",
            "observed_at": (today - timedelta(days=1)).isoformat(),
        }]

        season, source = engine._resolve_perennial_season(apple, today, observations)
        assert season == PerennialSeason.BUD_BREAK
        assert source == "auto-calendar"


class TestObservationFreshness:
    def test_recent_observation_trusted(self):
        engine = SmartGardenerEngine()
        plant = _make_plant()
        today = date(2026, 6, 25)

        observations = [{
            "scope": "plot",
            "observed_perennial_season": "flowering_fruit_set",
            "observed_at": (today - timedelta(days=2)).isoformat(),
        }]

        season, source = engine._resolve_perennial_season(plant, today, observations)
        assert season == PerennialSeason.FLOWERING_FRUIT_SET
        assert source == "user-observation"

    def test_stale_observation_ignored(self):
        engine = SmartGardenerEngine()
        plant = _make_plant()
        today = date(2026, 6, 25)

        observations = [{
            "scope": "plot",
            "observed_perennial_season": "bud_break",
            "observed_at": (today - timedelta(days=30)).isoformat(),
        }]

        season, source = engine._resolve_perennial_season(plant, today, observations)
        assert "stale" in source
        assert season == PerennialSeason.FRUIT_DEVELOPMENT

    def test_aged_observation_disagreeing_with_calendar_overridden(self):
        engine = SmartGardenerEngine()
        plant = _make_plant()
        today = date(2026, 6, 25)

        observations = [{
            "scope": "plot",
            "observed_perennial_season": "bud_break",
            "observed_at": (today - timedelta(days=14)).isoformat(),
        }]

        season, source = engine._resolve_perennial_season(plant, today, observations)
        assert season == PerennialSeason.FRUIT_DEVELOPMENT
        assert "superseded" in source

    def test_invalid_observed_phase_falls_back_to_auto(self):
        engine = SmartGardenerEngine()
        plant = _make_plant()
        today = date(2026, 4, 20)

        observations = [{
            "scope": "plot",
            "observed_perennial_season": "not-a-season",
            "observed_at": today.isoformat(),
        }]

        season, source = engine._resolve_perennial_season(plant, today, observations)
        assert season == PerennialSeason.BUD_BREAK
        assert source == "auto-calendar-invalid-obs"


class TestMultipleObservations:
    def test_latest_observation_wins(self):
        engine = SmartGardenerEngine()
        plant = _make_plant()
        today = date(2026, 4, 20)

        observations = [
            {
                "scope": "plot",
                "observed_perennial_season": "bud_break",
                "observed_at": (today - timedelta(days=10)).isoformat(),
            },
            {
                "scope": "plot",
                "observed_perennial_season": "flowering_fruit_set",
                "observed_at": (today - timedelta(days=2)).isoformat(),
            },
        ]

        season, _ = engine._resolve_perennial_season(plant, today, observations)
        assert season == PerennialSeason.FLOWERING_FRUIT_SET


class TestPerCellOverride:
    def test_single_cell_observation_only_affects_that_cell(self):
        engine = SmartGardenerEngine()
        apple_b3 = _make_plant(col=2, row=3)
        apple_d5 = _make_plant(col=4, row=5)
        today = date(2026, 4, 20)

        observations = [{
            "scope": "single",
            "cell_col": 2,
            "cell_row": 3,
            "observed_perennial_season": "flowering_fruit_set",
            "observed_at": today.isoformat(),
        }]

        season_b3, _ = engine._resolve_perennial_season(apple_b3, today, observations)
        season_d5, source_d5 = engine._resolve_perennial_season(apple_d5, today, observations)

        assert season_b3 == PerennialSeason.FLOWERING_FRUIT_SET
        assert season_d5 == PerennialSeason.BUD_BREAK
        assert source_d5 == "auto-calendar"
