"""Add species_filter and observed perennial season to garden observations.

Revision ID: 020_observation_species_filter
Revises: 019_lifecycle_type
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa


revision = "020_observation_species_filter"
down_revision = "019_lifecycle_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "garden_observations",
        sa.Column("species_filter", sa.JSON(), nullable=True),
    )
    op.add_column(
        "garden_observations",
        sa.Column("observed_perennial_season", sa.String(40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("garden_observations", "observed_perennial_season")
    op.drop_column("garden_observations", "species_filter")
