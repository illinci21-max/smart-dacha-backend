"""Sanitize existing plant profile data.

Revision ID: 009_sanitize_profiles
Revises: 008_plant_profiles_schema
"""

from alembic import op


revision = "009_sanitize_profiles"
down_revision = "008_plant_profiles_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE plant_profiles
        SET name_normalized = lower(trim(regexp_replace(name, '\\s+', ' ', 'g')))
        WHERE name_normalized IS NULL OR trim(name_normalized) = ''
        """
    )
    op.execute(
        """
        UPDATE plant_profiles
        SET name_normalized = CASE name_normalized
            WHEN 'помідор' THEN 'томат'
            WHEN 'помідори' THEN 'томат'
            WHEN 'помидор' THEN 'томат'
            WHEN 'помидоры' THEN 'томат'
            WHEN 'томати' THEN 'томат'
            WHEN 'tomato' THEN 'томат'
            WHEN 'tomatoes' THEN 'томат'
            WHEN 'картошка' THEN 'картопля'
            WHEN 'картофель' THEN 'картопля'
            WHEN 'potato' THEN 'картопля'
            WHEN 'potatoes' THEN 'картопля'
            WHEN 'огурец' THEN 'огірок'
            WHEN 'огурцы' THEN 'огірок'
            WHEN 'огірки' THEN 'огірок'
            WHEN 'cucumber' THEN 'огірок'
            WHEN 'cucumbers' THEN 'огірок'
            ELSE name_normalized
        END
        """
    )
    op.execute(
        """
        UPDATE plant_profiles
        SET
            kc_initial = LEAST(GREATEST(COALESCE(kc_initial, 0.40), 0.15), 0.85),
            kc_mid = LEAST(GREATEST(COALESCE(kc_mid, 1.05), 0.45), 1.35),
            kc_end = LEAST(GREATEST(COALESCE(kc_end, 0.70), 0.20), 1.15),
            initial_days = LEAST(GREATEST(COALESCE(initial_days, 20), 5), 80),
            development_days = LEAST(GREATEST(COALESCE(development_days, 30), 5), 90),
            mid_season_days = LEAST(GREATEST(COALESCE(mid_season_days, 35), 5), 120),
            late_season_days = LEAST(GREATEST(COALESCE(late_season_days, 20), 5), 90),
            root_depth_initial_cm = LEAST(GREATEST(COALESCE(root_depth_initial_cm, 10), 3), 80),
            root_depth_max_cm = LEAST(GREATEST(COALESCE(root_depth_max_cm, 50), 10), 250),
            field_capacity_mm = LEAST(GREATEST(COALESCE(field_capacity_mm, 180), 60), 320),
            wilting_point_mm = LEAST(GREATEST(COALESCE(wilting_point_mm, 55), 20), 180),
            critical_depletion = LEAST(GREATEST(COALESCE(critical_depletion, 0.50), 0.20), 0.75),
            t_min_growth = LEAST(GREATEST(COALESCE(t_min_growth, 8), -5), 20),
            t_optimal_min = LEAST(GREATEST(COALESCE(t_optimal_min, 18), 5), 30),
            t_optimal_max = LEAST(GREATEST(COALESCE(t_optimal_max, 28), 10), 40),
            t_max_growth = LEAST(GREATEST(COALESCE(t_max_growth, 38), 20), 50),
            frost_tolerance = LEAST(GREATEST(COALESCE(frost_tolerance, 0), -35), 8),
            nitrogen = LEAST(GREATEST(COALESCE(nitrogen, 2.0), 0), 8),
            phosphorus = LEAST(GREATEST(COALESCE(phosphorus, 1.0), 0), 5),
            potassium = LEAST(GREATEST(COALESCE(potassium, 2.0), 0), 8),
            magnesium = LEAST(GREATEST(COALESCE(magnesium, 0.3), 0), 3),
            calcium = LEAST(GREATEST(COALESCE(calcium, 0.5), 0), 5),
            sus_late_blight = LEAST(GREATEST(COALESCE(sus_late_blight, 0.3), 0), 1),
            sus_powdery_mildew = LEAST(GREATEST(COALESCE(sus_powdery_mildew, 0.3), 0), 1),
            sus_downy_mildew = LEAST(GREATEST(COALESCE(sus_downy_mildew, 0.3), 0), 1),
            sus_botrytis = LEAST(GREATEST(COALESCE(sus_botrytis, 0.2), 0), 1),
            days_to_harvest_min = LEAST(GREATEST(COALESCE(days_to_harvest_min, 60), 15), 365),
            days_to_harvest_max = LEAST(GREATEST(COALESCE(days_to_harvest_max, 90), 20), 450),
            created_at = COALESCE(created_at, NOW())
        """
    )
    op.execute(
        """
        UPDATE plant_profiles
        SET root_depth_initial_cm = root_depth_max_cm
        WHERE root_depth_initial_cm > root_depth_max_cm
        """
    )
    op.execute(
        """
        UPDATE plant_profiles
        SET wilting_point_mm = GREATEST(20, field_capacity_mm * 0.35)
        WHERE wilting_point_mm >= field_capacity_mm
        """
    )
    op.execute(
        """
        UPDATE plant_profiles
        SET t_min_growth = t_optimal_min - 2
        WHERE t_min_growth >= t_optimal_min
        """
    )
    op.execute(
        """
        UPDATE plant_profiles
        SET t_max_growth = t_optimal_max + 3
        WHERE t_max_growth <= t_optimal_max
        """
    )
    op.execute(
        """
        UPDATE plant_profiles
        SET
            days_to_harvest_min = LEAST(days_to_harvest_min, days_to_harvest_max),
            days_to_harvest_max = GREATEST(days_to_harvest_min, days_to_harvest_max)
        """
    )


def downgrade() -> None:
    # Data cleanup is intentionally irreversible.
    pass
