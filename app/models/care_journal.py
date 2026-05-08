# FIX: server_default=func.now() замість default=datetime.utcnow
# FIX: user_id додано nullable=False явно
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import String, DateTime, Boolean, ForeignKey, Text, func, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base

if TYPE_CHECKING:
    from app.models.ai_diagnosis import AIDiagnosis
    from app.models.plant import Plant


class CareJournal(Base):
    __tablename__ = "care_journal"
    __table_args__ = (
        Index("ix_care_journal_plant_deleted_performed", "plant_id", "is_deleted", text("performed_at DESC")),
        Index("ix_care_journal_user_updated", "user_id", "updated_at"),
    )

    # UUID генерується на клієнті — ключ для офлайн-синхронізації
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False, index=True
    )

    care_type: Mapped[str] = mapped_column(String(30), nullable=False,
        comment="watering|fertilizing|pest_treatment|pruning|harvesting|transplanting|observation|other"
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list] = mapped_column(JSONB, default=list)

    ai_diagnosis_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_diagnoses.id", ondelete="SET NULL")
    )

    # Офлайн-синхронізація
    device_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # FIX: server_default + onupdate для правильного timezone-aware поведінки
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    plant: Mapped["Plant"] = relationship(back_populates="journal_entries")
    ai_diagnosis: Mapped["AIDiagnosis | None"] = relationship(
        foreign_keys=[ai_diagnosis_id], lazy="select"
    )
