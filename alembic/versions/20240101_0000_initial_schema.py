"""Initial schema — all tables.

Revision ID: 001_initial
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "timescaledb" CASCADE')

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(100)),
        sa.Column("subscription_tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("subscription_expires_at", sa.DateTime(timezone=True)),
        sa.Column("stripe_customer_id", sa.String(100), unique=True),
        sa.Column("plots_limit", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("plants_limit", sa.SmallInteger(), nullable=False, server_default="10"),
        sa.Column("fcm_token", sa.String(500)),
        sa.Column("apns_token", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # weather_zones
    op.create_table(
        "weather_zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("lat_grid", sa.Numeric(6, 1), nullable=False),
        sa.Column("lon_grid", sa.Numeric(6, 1), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("country_code", sa.String(2)),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("lat_grid", "lon_grid", name="uq_weather_zone_grid"),
    )

    # weather_daily_cache (TimescaleDB hypertable)
    op.create_table(
        "weather_daily_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("temp_max", sa.Numeric(5, 2)),
        sa.Column("temp_min", sa.Numeric(5, 2)),
        sa.Column("temp_avg", sa.Numeric(5, 2)),
        sa.Column("precipitation", sa.Numeric(6, 2)),
        sa.Column("rain_probability", sa.Numeric(5, 2)),
        sa.Column("solar_radiation", sa.Numeric(8, 2)),
        sa.Column("wind_speed", sa.Numeric(5, 2)),
        sa.Column("is_forecast", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source_api", sa.String(50), server_default="open_meteo"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("zone_id", "date", name="uq_weather_cache_zone_date"),
    )
    # Перетворюємо на TimescaleDB hypertable
    op.execute("""
        SELECT create_hypertable(
            'weather_daily_cache', 'date',
            chunk_time_interval => INTERVAL '3 months',
            if_not_exists => TRUE
        )
    """)

    # crop_catalog
    op.create_table(
        "crop_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name_uk", sa.String(100), nullable=False),
        sa.Column("name_en", sa.String(100)),
        sa.Column("scientific_name", sa.String(150)),
        sa.Column("category", sa.String(50)),
        sa.Column("t_base", sa.Numeric(4, 1), nullable=False, server_default="10.0"),
        sa.Column("t_optimal_min", sa.Numeric(4, 1)),
        sa.Column("t_optimal_max", sa.Numeric(4, 1)),
        sa.Column("water_need_ml_per_day", sa.Integer()),
        sa.Column("drought_tolerance", sa.SmallInteger()),
        sa.Column("sun_requirement", sa.String(20)),
        sa.Column("min_daily_sun_hours", sa.Numeric(3, 1)),
        sa.Column("growth_stages", postgresql.JSONB(), server_default="[]"),
        sa.Column("common_diseases", postgresql.JSONB(), server_default="[]"),
        sa.Column("description", sa.Text()),
        sa.Column("icon_url", sa.String(500)),
        sa.Column("is_system", sa.Boolean(), server_default="true"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    # plots
    op.create_table(
        "plots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("zone_id", postgresql.UUID(as_uuid=True)),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("latitude", sa.Numeric(9, 6)),
        sa.Column("longitude", sa.Numeric(9, 6)),
        sa.Column("area_sqm", sa.Numeric(8, 2)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["zone_id"], ["weather_zones.id"]),
    )

    # plants
    op.create_table(
        "plants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100)),
        sa.Column("quantity", sa.SmallInteger(), server_default="1"),
        sa.Column("planted_date", sa.Date()),
        sa.Column("sat_accumulated", sa.Numeric(8, 2), server_default="0.0"),
        sa.Column("sat_reset_date", sa.Date()),
        sa.Column("current_growth_stage", sa.String(100)),
        sa.Column("insolation_accumulated_wh", sa.Numeric(12, 2), server_default="0.0"),
        sa.Column("last_watered_at", sa.DateTime(timezone=True)),
        sa.Column("next_watering_recommended_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["plot_id"], ["plots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["crop_id"], ["crop_catalog.id"]),
    )

    # ai_diagnoses
    op.create_table(
        "ai_diagnoses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("photo_url", sa.String(500), nullable=False),
        sa.Column("photo_taken_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("results", postgresql.JSONB(), server_default="[]"),
        sa.Column("model_version", sa.String(50)),
        sa.Column("processing_time_ms", sa.Integer()),
        sa.Column("error_message", sa.Text()),
        sa.Column("user_feedback", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )

    # care_journal
    op.create_table(
        "care_journal",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("care_type", sa.String(30), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(), server_default="{}"),
        sa.Column("notes", sa.Text()),
        sa.Column("photos", postgresql.JSONB(), server_default="[]"),
        sa.Column("ai_diagnosis_id", postgresql.UUID(as_uuid=True)),
        sa.Column("device_created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("synced_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ai_diagnosis_id"], ["ai_diagnoses.id"]),
    )

    # watering_recommendations
    op.create_table(
        "watering_recommendations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommended_date", sa.Date(), nullable=False),
        sa.Column("recommended_amount_ml", sa.Integer()),
        sa.Column("reason_factors", postgresql.JSONB(), server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("notification_sent_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("plant_id", "recommended_date", name="uq_watering_plant_date"),
    )

    # subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("stripe_subscription_id", sa.String(100), unique=True),
        sa.Column("stripe_price_id", sa.String(100)),
        sa.Column("price_usd", sa.Numeric(8, 2)),
        sa.Column("billing_cycle", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )

    # ── Індекси ────────────────────────────────────────────────────────────────
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_subscription", "users", ["subscription_tier", "subscription_expires_at"])
    op.create_index("idx_weather_zones_grid", "weather_zones", ["lat_grid", "lon_grid"])
    op.create_index("idx_weather_cache_zone_date", "weather_daily_cache", ["zone_id", sa.text("date DESC")])
    op.create_index("idx_plots_user", "plots", ["user_id"], postgresql_where=sa.text("is_deleted = FALSE"))
    op.create_index("idx_plants_user", "plants", ["user_id"], postgresql_where=sa.text("is_deleted = FALSE"))
    op.create_index("idx_plants_plot", "plants", ["plot_id"], postgresql_where=sa.text("is_deleted = FALSE"))
    op.create_index("idx_journal_plant_date", "care_journal", ["plant_id", sa.text("performed_at DESC")],
                    postgresql_where=sa.text("is_deleted = FALSE"))
    op.create_index("idx_journal_sync", "care_journal", ["user_id", "updated_at"],
                    postgresql_where=sa.text("synced_at IS NULL"))
    op.create_index("idx_diagnoses_user", "ai_diagnoses", ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_diagnoses_status", "ai_diagnoses", ["status"],
                    postgresql_where=sa.text("status IN ('pending', 'processing')"))
    op.create_index("idx_watering_plant_date", "watering_recommendations", ["plant_id", "recommended_date"])
    op.create_index("idx_subscriptions_user", "subscriptions", ["user_id", "status"])


def downgrade() -> None:
    for tbl in [
        "subscriptions", "watering_recommendations", "care_journal",
        "ai_diagnoses", "plants", "plots", "crop_catalog",
        "weather_daily_cache", "weather_zones", "users",
    ]:
        op.drop_table(tbl)
