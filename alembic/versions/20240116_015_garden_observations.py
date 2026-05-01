"""Add manual garden observations.

Revision ID: 015_garden_observations
Revises: 014_work_plan_suppression
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "015_garden_observations"
down_revision = "014_work_plan_suppression"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("garden_observations"):
        return

    op.create_table(
        "garden_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="plot"),
        sa.Column("plant_type", sa.String(length=100), nullable=True),
        sa.Column("variety", sa.String(length=100), nullable=True),
        sa.Column("cell_col", sa.Integer(), nullable=True),
        sa.Column("cell_row", sa.Integer(), nullable=True),
        sa.Column("soil_moisture_pct", sa.Integer(), nullable=True),
        sa.Column("soil_moisture_status", sa.String(length=20), nullable=True),
        sa.Column("leaf_condition", sa.String(length=40), nullable=True),
        sa.Column("symptoms", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("growth_phase", sa.String(length=30), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_garden_observations_observed_at", "garden_observations", ["observed_at"])
    op.create_index("ix_garden_observations_plot_observed", "garden_observations", ["plot_id", sa.text("observed_at DESC")])
    op.create_index(
        "ix_garden_observations_lookup",
        "garden_observations",
        ["plot_id", "plant_type", "variety", "cell_col", "cell_row"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("garden_observations"):
        return
    indexes = {idx["name"] for idx in inspector.get_indexes("garden_observations")}
    for name in [
        "ix_garden_observations_lookup",
        "ix_garden_observations_plot_observed",
        "ix_garden_observations_observed_at",
    ]:
        if name in indexes:
            op.drop_index(name, table_name="garden_observations")
    op.drop_table("garden_observations")
