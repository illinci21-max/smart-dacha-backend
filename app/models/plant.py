# FIX: server_default=func.now() замість default=datetime.utcnow
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import String, Numeric, DateTime, Date, Boolean, ForeignKey, Integer, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base
from app.services.lifecycle_types import LifecycleType

if TYPE_CHECKING:
    from app.models.care_journal import CareJournal
    from app.models.crop import CropCatalog
    from app.models.plot import Plot
    from app.models.watering import WateringRecommendation


class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plots.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False, index=True
    )
    crop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("crop_catalog.id"),
        nullable=False, index=True
    )

    name: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(SmallInteger, default=1)
    planted_date: Mapped[date | None] = mapped_column(Date)
    lifecycle_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="annual",
        server_default="annual",
    )
    planting_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sat_accumulated: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0.0)
    sat_reset_date: Mapped[date | None] = mapped_column(Date)
    sat_last_updated_at: Mapped[date | None] = mapped_column(Date)
    current_growth_stage: Mapped[str | None] = mapped_column(String(100))

    insolation_accumulated_wh: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0.0)

    last_watered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_watering_recommended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    plot: Mapped["Plot"] = relationship(back_populates="plants")
    crop: Mapped["CropCatalog"] = relationship(back_populates="plants")
    journal_entries: Mapped[list["CareJournal"]] = relationship(
        back_populates="plant", lazy="select"
    )
    watering_recs: Mapped[list["WateringRecommendation"]] = relationship(
        back_populates="plant", lazy="select"
    )

    @property
    def lifecycle(self) -> LifecycleType:
        """Typed enum accessor."""
        try:
            return LifecycleType(self.lifecycle_type)
        except ValueError:
            return LifecycleType.ANNUAL

    @property
    def age_years(self) -> int | None:
        """Years since planting, used by perennial logic."""
        if self.planting_year is None:
            return None
        return max(0, date.today().year - self.planting_year)
