import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from sqlalchemy import String, Numeric, SmallInteger, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base

if TYPE_CHECKING:
    from app.models.plant import Plant


class CropCatalog(Base):
    __tablename__ = "crop_catalog"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name_uk: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str | None] = mapped_column(String(100))
    scientific_name: Mapped[str | None] = mapped_column(String(150))
    category: Mapped[str | None] = mapped_column(String(50))
    emoji: Mapped[str | None] = mapped_column(String(10))
    lifecycle_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="annual",
        server_default="annual",
    )

    # Агрономічні норми
    t_base: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=10.0,
        comment="Базова температура для розрахунку САТ (°C)")
    t_optimal_min: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    t_optimal_max: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    # Полив
    water_need_ml_per_day: Mapped[int | None] = mapped_column()
    drought_tolerance: Mapped[int | None] = mapped_column(SmallInteger,
        comment="1=дуже вибаглива, 5=посухостійка")

    # Сонце
    sun_requirement: Mapped[str | None] = mapped_column(String(20))
    min_daily_sun_hours: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))

    # Фази росту та хвороби (JSONB)
    growth_stages: Mapped[list | None] = mapped_column(JSONB, default=list,
        comment='[{"name":"сходи","sat_from":0,"sat_to":150}]')
    common_diseases: Mapped[list | None] = mapped_column(JSONB, default=list,
        comment='[{"id":"late_blight","name":"Фітофтора"}]')
    care_tips: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    description: Mapped[str | None] = mapped_column(Text)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    plants: Mapped[list["Plant"]] = relationship(back_populates="crop", lazy="select")
