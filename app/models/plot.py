# FIX: server_default=func.now() замість default=datetime.utcnow
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, Boolean, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class Plot(Base):
    __tablename__ = "plots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    zone_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("weather_zones.id", ondelete="SET NULL"), index=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    elevation_m: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    soil_type: Mapped[str] = mapped_column(String(30), nullable=False, default="loam", server_default="loam")
    plot_ph_class: Mapped[str | None] = mapped_column(String(30))
    plot_drainage_class: Mapped[str | None] = mapped_column(String(30))
    plot_organic_input: Mapped[str | None] = mapped_column(String(30))
    plot_last_season_quality: Mapped[str | None] = mapped_column(String(30))
    plot_user_survey: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Garden grid planner layout (JSON: {cols, rows, cells: [...]})
    grid_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # FIX: server_default=func.now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="plots")
    zone: Mapped["WeatherZone | None"] = relationship(back_populates="plots")
    plants: Mapped[list["Plant"]] = relationship(back_populates="plot", lazy="select")
    garden_actions: Mapped[list["GardenAction"]] = relationship(
        back_populates="plot", lazy="select", cascade="all, delete-orphan"
    )
    garden_observations: Mapped[list["GardenObservation"]] = relationship(
        back_populates="plot", lazy="select", cascade="all, delete-orphan"
    )

