"""Tests for coarse perennial seasonal phenology."""
from datetime import date

import pytest

from app.services.lifecycle_types import LifecycleType, PerennialSeason
from app.services.perennial_phenology import (
    determine_perennial_season,
    is_plant_productive,
)


class TestSeasonMapping:
    def test_january_is_dormant_winter(self):
        season = determine_perennial_season(
            date(2026, 1, 15),
            LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
        )

        assert season == PerennialSeason.DORMANT_WINTER

    def test_april_is_bud_break(self):
        season = determine_perennial_season(
            date(2026, 4, 10),
            LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
        )

        assert season == PerennialSeason.BUD_BREAK

    def test_early_june_is_flowering(self):
        season = determine_perennial_season(
            date(2026, 6, 5),
            LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
        )

        assert season == PerennialSeason.FLOWERING_FRUIT_SET

    def test_late_june_is_fruit_development(self):
        season = determine_perennial_season(
            date(2026, 6, 25),
            LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
        )

        assert season == PerennialSeason.FRUIT_DEVELOPMENT

    def test_august_is_harvest(self):
        season = determine_perennial_season(
            date(2026, 8, 15),
            LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
        )

        assert season == PerennialSeason.HARVEST_RIPENING


class TestProductiveAge:
    def test_young_apple_skips_flowering(self):
        season = determine_perennial_season(
            date(2026, 5, 15),
            LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
            is_productive=False,
        )

        assert season == PerennialSeason.FRUIT_DEVELOPMENT

    def test_mature_apple_flowers_normally(self):
        season = determine_perennial_season(
            date(2026, 5, 15),
            LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
            is_productive=True,
        )

        assert season == PerennialSeason.FLOWERING_FRUIT_SET

    def test_strawberry_productive_year_1(self):
        assert is_plant_productive(1, LifecycleType.PERENNIAL_HERBACEOUS) is True

    def test_apple_not_productive_year_2(self):
        assert is_plant_productive(2, LifecycleType.PERENNIAL_WOODY_DECIDUOUS) is False

    def test_apple_productive_year_5(self):
        assert is_plant_productive(5, LifecycleType.PERENNIAL_WOODY_DECIDUOUS) is True


class TestNonPerennialRejected:
    def test_annual_raises(self):
        with pytest.raises(ValueError, match="non-perennial"):
            determine_perennial_season(date(2026, 5, 1), LifecycleType.ANNUAL)


class TestEngineIntegration:
    def test_old_apple_does_not_get_late_season_in_spring(self):
        from app.services.smart_gardener_engine import (
            GrowthPhase,
            KcStages,
            PlantInstance,
            SmartGardenerEngine,
        )

        engine = SmartGardenerEngine()
        plant = PlantInstance(
            cell_col=0,
            cell_row=0,
            plant_type="Яблуня",
            planted_date="2022-04-01",
            category="Дерева",
            lifecycle_type=LifecycleType.PERENNIAL_WOODY_DECIDUOUS,
            age_years=4,
        )

        phase, _kc = engine.determine_growth_phase(
            plant.age_days,
            KcStages(),
            plant=plant,
            today=date(2026, 5, 10),
        )

        assert phase != GrowthPhase.LATE_SEASON
        assert phase == GrowthPhase.DEVELOPMENT
        assert plant.perennial_season == PerennialSeason.FLOWERING_FRUIT_SET

    def test_parse_grid_cells_reads_lifecycle_and_age_years(self):
        from app.services.smart_gardener_engine import SmartGardenerEngine

        plants = SmartGardenerEngine._parse_grid_cells(
            [
                {
                    "col": 1,
                    "row": 2,
                    "plant_type": "Яблуня",
                    "lifecycle_type": "perennial_woody_deciduous",
                    "planting_year": 2022,
                }
            ],
            date(2026, 5, 10),
        )

        assert plants[0].lifecycle_type == LifecycleType.PERENNIAL_WOODY_DECIDUOUS
        assert plants[0].age_years == 4
