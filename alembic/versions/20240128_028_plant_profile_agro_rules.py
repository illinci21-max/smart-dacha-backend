"""Add plant profile agro-analysis rules.

Revision ID: 028_plant_profile_agro_rules
Revises: 027_crop_catalog_care_tips
"""
from alembic import op
import sqlalchemy as sa

revision = "028_plant_profile_agro_rules"
down_revision = "027_crop_catalog_care_tips"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plant_profiles", sa.Column("disease_protection_adaptation_days", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("plant_profiles", sa.Column("disease_protection_early_symptom_days", sa.Integer(), nullable=False, server_default="2"))
    op.add_column("plant_profiles", sa.Column("biofungicide_allowed_from_day", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("plant_profiles", sa.Column("chemical_fungicide_allowed_from_day", sa.Integer(), nullable=False, server_default="5"))
    op.add_column("plant_profiles", sa.Column("copper_fungicide_allowed_from_day", sa.Integer(), nullable=False, server_default="7"))
    op.add_column("plant_profiles", sa.Column("max_spray_temp_c", sa.Float(), nullable=False, server_default="28"))
    op.add_column("plant_profiles", sa.Column("avoid_spray_before_rain_hours", sa.Integer(), nullable=False, server_default="6"))
    op.add_column("plant_profiles", sa.Column("cold_stress_threshold_c", sa.Float(), nullable=True))
    op.add_column("plant_profiles", sa.Column("frost_critical_threshold_c", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("plant_profiles", "frost_critical_threshold_c")
    op.drop_column("plant_profiles", "cold_stress_threshold_c")
    op.drop_column("plant_profiles", "avoid_spray_before_rain_hours")
    op.drop_column("plant_profiles", "max_spray_temp_c")
    op.drop_column("plant_profiles", "copper_fungicide_allowed_from_day")
    op.drop_column("plant_profiles", "chemical_fungicide_allowed_from_day")
    op.drop_column("plant_profiles", "biofungicide_allowed_from_day")
    op.drop_column("plant_profiles", "disease_protection_early_symptom_days")
    op.drop_column("plant_profiles", "disease_protection_adaptation_days")
