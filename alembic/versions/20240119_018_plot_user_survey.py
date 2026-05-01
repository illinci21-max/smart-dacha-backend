"""Add user soil survey fields to plots.

Revision ID: 018_plot_user_survey
Revises: 017_plant_sat_last_updated
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "018_plot_user_survey"
down_revision = "017_plant_sat_last_updated"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plots", sa.Column("plot_ph_class", sa.String(length=30), nullable=True))
    op.add_column("plots", sa.Column("plot_drainage_class", sa.String(length=30), nullable=True))
    op.add_column("plots", sa.Column("plot_organic_input", sa.String(length=30), nullable=True))
    op.add_column("plots", sa.Column("plot_last_season_quality", sa.String(length=30), nullable=True))
    op.add_column("plots", sa.Column("plot_user_survey", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("plots", "plot_user_survey")
    op.drop_column("plots", "plot_last_season_quality")
    op.drop_column("plots", "plot_organic_input")
    op.drop_column("plots", "plot_drainage_class")
    op.drop_column("plots", "plot_ph_class")
