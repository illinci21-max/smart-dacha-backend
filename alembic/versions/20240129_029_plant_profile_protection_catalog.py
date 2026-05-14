"""Add plant profile protection knowledge catalog.

Revision ID: 029_profile_protection_catalog
Revises: 028_plant_profile_agro_rules
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "029_profile_protection_catalog"
down_revision = "028_plant_profile_agro_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "plant_profiles",
        sa.Column(
            "common_diseases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "plant_profiles",
        sa.Column(
            "common_pests",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "plant_profiles",
        sa.Column(
            "treatment_guide",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("plant_profiles", "treatment_guide")
    op.drop_column("plant_profiles", "common_pests")
    op.drop_column("plant_profiles", "common_diseases")
