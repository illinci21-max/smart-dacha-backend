"""Add lifecycle_type to crop_catalog and plants.

Revision ID: 019_lifecycle_type
Revises: 018_plot_user_survey
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa


revision = "019_lifecycle_type"
down_revision = "018_plot_user_survey"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crop_catalog",
        sa.Column(
            "lifecycle_type",
            sa.String(40),
            nullable=False,
            server_default="annual",
        ),
    )
    op.create_index(
        "ix_crop_catalog_lifecycle_type",
        "crop_catalog",
        ["lifecycle_type"],
    )

    op.add_column(
        "plants",
        sa.Column(
            "lifecycle_type",
            sa.String(40),
            nullable=False,
            server_default="annual",
        ),
    )
    op.add_column(
        "plants",
        sa.Column("planting_year", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE plants
        SET planting_year = EXTRACT(YEAR FROM planted_date)::INTEGER
        WHERE planted_date IS NOT NULL AND planting_year IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("plants", "planting_year")
    op.drop_column("plants", "lifecycle_type")
    op.drop_index("ix_crop_catalog_lifecycle_type", table_name="crop_catalog")
    op.drop_column("crop_catalog", "lifecycle_type")
