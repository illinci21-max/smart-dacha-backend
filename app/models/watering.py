# FIX: server_default=func.now()
import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, DateTime, Date, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class WateringRecommendation(Base):
    __tablename__ = "watering_recommendations"
    __table_args__ = (
        UniqueConstraint("plant_id", "recommended_date", name="uq_watering_plant_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    recommended_date: Mapped[date] = mapped_column(Date, nullable=False)
    recommended_amount_ml: Mapped[int | None] = mapped_column(Integer)

    reason_factors: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False,
        comment="pending|done|skipped|rain_cancelled"
    )
    notification_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    plant: Mapped["Plant"] = relationship(back_populates="watering_recs")
