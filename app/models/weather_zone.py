# FIX: Єдина версія WeatherZone (об'єднано з weather.py, видалено дублікат)
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class WeatherZone(Base):
    __tablename__ = "weather_zones"
    __table_args__ = (
        UniqueConstraint("lat_grid", "lon_grid", name="uq_weather_zones_grid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lat_grid: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)
    lon_grid: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(String(2))
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # FIX: використовуємо server_default=func.now() замість datetime.utcnow (deprecated)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    plots: Mapped[list["Plot"]] = relationship(back_populates="zone", lazy="select")
    weather_cache: Mapped[list["WeatherDailyCache"]] = relationship(
        back_populates="zone", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<WeatherZone ({self.lat_grid}, {self.lon_grid})>"
