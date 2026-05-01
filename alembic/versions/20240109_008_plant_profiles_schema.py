"""Add plant_profiles schema to migrations.

Revision ID: 008_plant_profiles_schema
Revises: 007_garden_actions_table
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "008_plant_profiles_schema"
down_revision = "007_garden_actions_table"
branch_labels = None
depends_on = None


FLOAT_DEFAULTS = {
    "kc_initial": 0.40,
    "kc_mid": 1.05,
    "kc_end": 0.70,
    "root_depth_initial_cm": 10,
    "root_depth_max_cm": 50,
    "field_capacity_mm": 180,
    "wilting_point_mm": 55,
    "critical_depletion": 0.50,
    "t_min_growth": 8,
    "t_optimal_min": 18,
    "t_optimal_max": 28,
    "t_max_growth": 38,
    "frost_tolerance": 0,
    "nitrogen": 2.0,
    "phosphorus": 1.0,
    "potassium": 2.0,
    "magnesium": 0.3,
    "calcium": 0.5,
    "sus_late_blight": 0.3,
    "sus_powdery_mildew": 0.3,
    "sus_downy_mildew": 0.3,
    "sus_botrytis": 0.2,
}

INT_DEFAULTS = {
    "initial_days": 20,
    "development_days": 30,
    "mid_season_days": 35,
    "late_season_days": 20,
    "days_to_harvest_min": 60,
    "days_to_harvest_max": 90,
}


def _index_names(inspector: sa.Inspector) -> set[str]:
    return {idx["name"] for idx in inspector.get_indexes("plant_profiles")}


def _unique_names(inspector: sa.Inspector) -> set[str]:
    return {uc["name"] for uc in inspector.get_unique_constraints("plant_profiles")}


def _create_table() -> None:
    op.create_table(
        "plant_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_normalized", sa.String(100)),
        sa.Column("category", sa.String(50)),
        sa.Column("emoji", sa.String(10)),
        sa.Column("kc_initial", sa.Float(), nullable=False),
        sa.Column("kc_mid", sa.Float(), nullable=False),
        sa.Column("kc_end", sa.Float(), nullable=False),
        sa.Column("initial_days", sa.Integer(), nullable=False),
        sa.Column("development_days", sa.Integer(), nullable=False),
        sa.Column("mid_season_days", sa.Integer(), nullable=False),
        sa.Column("late_season_days", sa.Integer(), nullable=False),
        sa.Column("root_depth_initial_cm", sa.Float(), nullable=False),
        sa.Column("root_depth_max_cm", sa.Float(), nullable=False),
        sa.Column("field_capacity_mm", sa.Float(), nullable=False),
        sa.Column("wilting_point_mm", sa.Float(), nullable=False),
        sa.Column("critical_depletion", sa.Float(), nullable=False),
        sa.Column("t_min_growth", sa.Float(), nullable=False),
        sa.Column("t_optimal_min", sa.Float(), nullable=False),
        sa.Column("t_optimal_max", sa.Float(), nullable=False),
        sa.Column("t_max_growth", sa.Float(), nullable=False),
        sa.Column("frost_tolerance", sa.Float(), nullable=False),
        sa.Column("nitrogen", sa.Float(), nullable=False),
        sa.Column("phosphorus", sa.Float(), nullable=False),
        sa.Column("potassium", sa.Float(), nullable=False),
        sa.Column("magnesium", sa.Float(), nullable=False),
        sa.Column("calcium", sa.Float(), nullable=False),
        sa.Column("sus_late_blight", sa.Float(), nullable=False),
        sa.Column("sus_powdery_mildew", sa.Float(), nullable=False),
        sa.Column("sus_downy_mildew", sa.Float(), nullable=False),
        sa.Column("sus_botrytis", sa.Float(), nullable=False),
        sa.Column("days_to_harvest_min", sa.Integer(), nullable=False),
        sa.Column("days_to_harvest_max", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(20)),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="plant_profiles_name_key"),
    )


def _ensure_indexes(inspector: sa.Inspector) -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    indexes = _index_names(inspector)
    if "ix_plant_profiles_name" not in indexes:
        op.create_index("ix_plant_profiles_name", "plant_profiles", ["name"])
    if "ix_plant_profiles_name_normalized" not in indexes:
        op.create_index(
            "ix_plant_profiles_name_normalized",
            "plant_profiles",
            ["name_normalized"],
        )
    if "ix_plant_profiles_name_trgm" not in indexes:
        op.create_index(
            "ix_plant_profiles_name_trgm",
            "plant_profiles",
            ["name"],
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("plant_profiles"):
        _create_table()
        inspector = sa.inspect(bind)
    else:
        columns = {col["name"] for col in inspector.get_columns("plant_profiles")}
        if "name_normalized" not in columns:
            op.add_column("plant_profiles", sa.Column("name_normalized", sa.String(100)))

        for column, default in FLOAT_DEFAULTS.items():
            op.execute(
                sa.text(f"UPDATE plant_profiles SET {column} = :default WHERE {column} IS NULL")
                .bindparams(default=default)
            )
            op.alter_column(
                "plant_profiles",
                column,
                existing_type=sa.Float(),
                nullable=False,
            )

        for column, default in INT_DEFAULTS.items():
            op.execute(
                sa.text(f"UPDATE plant_profiles SET {column} = :default WHERE {column} IS NULL")
                .bindparams(default=default)
            )
            op.alter_column(
                "plant_profiles",
                column,
                existing_type=sa.Integer(),
                nullable=False,
            )

        op.execute("UPDATE plant_profiles SET created_at = NOW() WHERE created_at IS NULL")
        op.alter_column(
            "plant_profiles",
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )

        if "plant_profiles_name_key" not in _unique_names(inspector):
            op.create_unique_constraint(
                "plant_profiles_name_key",
                "plant_profiles",
                ["name"],
            )

    _ensure_indexes(sa.inspect(bind))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("plant_profiles"):
        return

    indexes = _index_names(inspector)
    for index_name in [
        "ix_plant_profiles_name_trgm",
        "ix_plant_profiles_name_normalized",
        "ix_plant_profiles_name",
    ]:
        if index_name in indexes:
            op.drop_index(index_name, table_name="plant_profiles")

    if "plant_profiles_name_key" in _unique_names(inspector):
        op.drop_constraint("plant_profiles_name_key", "plant_profiles", type_="unique")

    for column in FLOAT_DEFAULTS:
        op.alter_column("plant_profiles", column, existing_type=sa.Float(), nullable=True)
    for column in INT_DEFAULTS:
        op.alter_column("plant_profiles", column, existing_type=sa.Integer(), nullable=True)
    op.alter_column(
        "plant_profiles",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
