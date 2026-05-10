"""Add crop_catalog.care_tips.

Revision ID: 027_crop_catalog_care_tips
Revises: 026_crop_catalog_emoji
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "027_crop_catalog_care_tips"
down_revision = "026_crop_catalog_emoji"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "crop_catalog",
        sa.Column(
            "care_tips",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("crop_catalog", "care_tips")
