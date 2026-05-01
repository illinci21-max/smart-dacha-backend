# FIX: Єдина версія AIDiagnosis (видалено дублікат diagnosis.py)
# FIX: server_default=func.now() замість default=datetime.utcnow (deprecated + timezone-unaware)
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class AIDiagnosis(Base):
    __tablename__ = "ai_diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False, index=True
    )
    plant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="SET NULL")
    )

    photo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    photo_taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending",
        comment="pending|processing|completed|failed"
    )

    results: Mapped[list] = mapped_column(JSONB, default=list, comment="""
    [{
        "disease_id": "late_blight",
        "disease_name": "Фітофтора",
        "confidence": 0.92,
        "severity": "moderate",
        "recommendations": ["..."],
        "bounding_box": {"x":100,"y":200,"w":50,"h":50}
    }]""")

    model_version: Mapped[str | None] = mapped_column(String(50))
    processing_time_ms: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    user_feedback: Mapped[str | None] = mapped_column(String(20),
        comment="correct|incorrect|unsure"
    )

    # FIX: server_default=func.now() для timezone-aware дат на рівні БД
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
