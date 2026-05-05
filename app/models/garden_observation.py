import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GardenObservation(Base):
    __tablename__ = "garden_observations"
    __table_args__ = (
        Index("ix_garden_observations_plot_observed", "plot_id", text("observed_at DESC")),
        Index(
            "ix_garden_observations_lookup",
            "plot_id",
            "plant_type",
            "variety",
            "cell_col",
            "cell_row",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plots.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="plot", server_default="plot")
    plant_type: Mapped[str | None] = mapped_column(String(100))
    variety: Mapped[str | None] = mapped_column(String(100))
    cell_col: Mapped[int | None] = mapped_column(Integer)
    cell_row: Mapped[int | None] = mapped_column(Integer)
    soil_moisture_pct: Mapped[int | None] = mapped_column(Integer)
    soil_moisture_status: Mapped[str | None] = mapped_column(String(20))
    leaf_condition: Mapped[str | None] = mapped_column(String(40))
    symptoms: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    growth_phase: Mapped[str | None] = mapped_column(String(30))
    species_filter: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True, default=None)
    observed_perennial_season: Mapped[str | None] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    plot: Mapped["Plot"] = relationship(back_populates="garden_observations")
    user: Mapped["User"] = relationship(back_populates="garden_observations")
