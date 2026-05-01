"""Add structured treatment applications journal.

Revision ID: 013_treatment_applications
Revises: 012_work_plan_items
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "013_treatment_applications"
down_revision = "012_work_plan_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("treatment_applications"):
        op.create_table(
            "treatment_applications",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("plot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plots.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("garden_action_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("garden_actions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("work_plan_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("work_plan_items.id", ondelete="SET NULL"), nullable=True),
            sa.Column("treatment_kind", sa.String(30), nullable=False),
            sa.Column("source", sa.String(30), nullable=False, server_default="work_plan"),
            sa.Column("plant_type", sa.String(100), nullable=True),
            sa.Column("variety", sa.String(100), nullable=True),
            sa.Column("cell_col", sa.Integer(), nullable=True),
            sa.Column("cell_row", sa.Integer(), nullable=True),
            sa.Column("scope", sa.String(20), nullable=False, server_default="single"),
            sa.Column("product_profile_id", sa.String(80), nullable=True),
            sa.Column("product_name", sa.String(160), nullable=True),
            sa.Column("product_type", sa.String(80), nullable=True),
            sa.Column("application_method", sa.String(80), nullable=True),
            sa.Column("target_problem", sa.String(120), nullable=True),
            sa.Column("frac_group", sa.String(30), nullable=True),
            sa.Column("n_pct", sa.Numeric(6, 2), nullable=True),
            sa.Column("p_pct", sa.Numeric(6, 2), nullable=True),
            sa.Column("k_pct", sa.Numeric(6, 2), nullable=True),
            sa.Column("mg_pct", sa.Numeric(6, 2), nullable=True),
            sa.Column("ca_pct", sa.Numeric(6, 2), nullable=True),
            sa.Column("reentry_days", sa.Integer(), nullable=True),
            sa.Column("pre_harvest_interval_days", sa.Integer(), nullable=True),
            sa.Column("rainfast_hours", sa.Integer(), nullable=True),
            sa.Column("rate_amount", sa.String(120), nullable=True),
            sa.Column("area_sqm", sa.Numeric(10, 2), nullable=True),
            sa.Column("applied_amount", sa.String(120), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("treatment_applications")}
    if "ix_treatment_plot_applied" not in indexes:
        op.execute("CREATE INDEX ix_treatment_plot_applied ON treatment_applications (plot_id, applied_at DESC)")
    if "ix_treatment_user_kind" not in indexes:
        op.create_index("ix_treatment_user_kind", "treatment_applications", ["user_id", "treatment_kind"])
    if "ix_treatment_action" not in indexes:
        op.create_index("ix_treatment_action", "treatment_applications", ["garden_action_id"])
    if "ix_treatment_work_plan" not in indexes:
        op.create_index("ix_treatment_work_plan", "treatment_applications", ["work_plan_item_id"])
    if "ix_treatment_applications_applied_at" not in indexes:
        op.create_index("ix_treatment_applications_applied_at", "treatment_applications", ["applied_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("treatment_applications"):
        indexes = {idx["name"] for idx in inspector.get_indexes("treatment_applications")}
        for name in (
            "ix_treatment_applications_applied_at",
            "ix_treatment_work_plan",
            "ix_treatment_action",
            "ix_treatment_user_kind",
            "ix_treatment_plot_applied",
        ):
            if name in indexes:
                op.drop_index(name, table_name="treatment_applications")
        op.drop_table("treatment_applications")
