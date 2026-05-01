"""Add explicit work plan suppression windows.

Revision ID: 014_work_plan_suppression
Revises: 013_treatment_applications
"""

from alembic import op
import sqlalchemy as sa


revision = "014_work_plan_suppression"
down_revision = "013_treatment_applications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("work_plan_items"):
        return

    columns = {column["name"] for column in inspector.get_columns("work_plan_items")}
    if "snoozed_until" not in columns:
        op.add_column("work_plan_items", sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True))
    if "suppressed_until" not in columns:
        op.add_column("work_plan_items", sa.Column("suppressed_until", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        """
        UPDATE work_plan_items
        SET suppressed_until =
            completed_at +
            CASE task_type
                WHEN 'watering' THEN INTERVAL '3 days'
                WHEN 'fertilizing' THEN INTERVAL '14 days'
                WHEN 'disease_protection' THEN INTERVAL '10 days'
                WHEN 'pest_control' THEN INTERVAL '10 days'
                WHEN 'pruning' THEN INTERVAL '14 days'
                WHEN 'harvesting' THEN INTERVAL '1 day'
                WHEN 'frost_protection' THEN INTERVAL '3 days'
                WHEN 'cold_stress' THEN INTERVAL '3 days'
                ELSE INTERVAL '3 days'
            END
        WHERE status = 'done'
          AND completed_at IS NOT NULL
          AND suppressed_until IS NULL
        """
    )

    indexes = {idx["name"] for idx in inspector.get_indexes("work_plan_items")}
    if "ix_work_plan_suppressed_until" not in indexes:
        op.create_index("ix_work_plan_suppressed_until", "work_plan_items", ["suppressed_until"])
    if "ix_work_plan_snoozed_until" not in indexes:
        op.create_index("ix_work_plan_snoozed_until", "work_plan_items", ["snoozed_until"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("work_plan_items"):
        return

    indexes = {idx["name"] for idx in inspector.get_indexes("work_plan_items")}
    if "ix_work_plan_snoozed_until" in indexes:
        op.drop_index("ix_work_plan_snoozed_until", table_name="work_plan_items")
    if "ix_work_plan_suppressed_until" in indexes:
        op.drop_index("ix_work_plan_suppressed_until", table_name="work_plan_items")

    columns = {column["name"] for column in inspector.get_columns("work_plan_items")}
    if "suppressed_until" in columns:
        op.drop_column("work_plan_items", "suppressed_until")
    if "snoozed_until" in columns:
        op.drop_column("work_plan_items", "snoozed_until")
