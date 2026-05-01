"""Add work plan items table.

Revision ID: 012_work_plan_items
Revises: 011_user_admin
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "012_work_plan_items"
down_revision = "011_user_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("work_plan_items"):
        op.create_table(
            "work_plan_items",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("plot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plots.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("recommendation_key", sa.String(80), nullable=False),
            sa.Column("source", sa.String(30), nullable=False, server_default="agro_analysis"),
            sa.Column("status", sa.String(20), nullable=False, server_default="planned"),
            sa.Column("task_type", sa.String(40), nullable=False),
            sa.Column("priority", sa.String(20), nullable=False, server_default="medium"),
            sa.Column("category", sa.String(40), nullable=False, server_default="general"),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("amount", sa.String(120), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("plant_type", sa.String(100), nullable=True),
            sa.Column("variety", sa.String(100), nullable=True),
            sa.Column("cell_col", sa.Integer(), nullable=True),
            sa.Column("cell_row", sa.Integer(), nullable=True),
            sa.Column("confidence", sa.Integer(), nullable=False, server_default="80"),
            sa.Column("recommendation_type", sa.String(120), nullable=True),
            sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("reason_groups", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("constraints", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("blocked_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("completed_action_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("garden_actions.id", ondelete="SET NULL"), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("plot_id", "user_id", "recommendation_key", name="uq_work_plan_recommendation"),
        )

    indexes = {idx["name"] for idx in sa.inspect(bind).get_indexes("work_plan_items")}
    if "ix_work_plan_plot_status_due" not in indexes:
        op.create_index("ix_work_plan_plot_status_due", "work_plan_items", ["plot_id", "status", "due_date"])
    if "ix_work_plan_user_status" not in indexes:
        op.create_index("ix_work_plan_user_status", "work_plan_items", ["user_id", "status"])
    if "ix_work_plan_created" not in indexes:
        op.execute("CREATE INDEX ix_work_plan_created ON work_plan_items (created_at DESC)")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("work_plan_items"):
        indexes = {idx["name"] for idx in inspector.get_indexes("work_plan_items")}
        if "ix_work_plan_created" in indexes:
            op.drop_index("ix_work_plan_created", table_name="work_plan_items")
        if "ix_work_plan_user_status" in indexes:
            op.drop_index("ix_work_plan_user_status", table_name="work_plan_items")
        if "ix_work_plan_plot_status_due" in indexes:
            op.drop_index("ix_work_plan_plot_status_due", table_name="work_plan_items")
        op.drop_table("work_plan_items")
