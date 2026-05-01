"""Persist plant profile confidence metadata.

Revision ID: 010_profile_confidence
Revises: 009_sanitize_profiles
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "010_profile_confidence"
down_revision = "009_sanitize_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("plant_profiles")}
    if "confidence" not in columns:
        op.add_column(
            "plant_profiles",
            sa.Column("confidence", sa.SmallInteger(), nullable=False, server_default="70"),
        )
    if "validation_warnings" not in columns:
        op.add_column(
            "plant_profiles",
            sa.Column("validation_warnings", postgresql.ARRAY(sa.Text()), nullable=True),
        )
    op.execute(
        """
        UPDATE plant_profiles
        SET confidence = CASE
            WHEN source = 'curated' THEN 95
            WHEN source = 'catalog' THEN 82
            WHEN source = 'gemini' THEN 70
            WHEN source = 'default' THEN 45
            ELSE COALESCE(confidence, 60)
        END
        WHERE confidence IS NULL OR confidence = 70
        """
    )
    op.execute(
        "UPDATE plant_profiles SET validation_warnings = ARRAY[]::text[] WHERE validation_warnings IS NULL"
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("plant_profiles")}
    if "validation_warnings" in columns:
        op.drop_column("plant_profiles", "validation_warnings")
    if "confidence" in columns:
        op.drop_column("plant_profiles", "confidence")
