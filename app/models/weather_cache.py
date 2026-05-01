# FIX: Єдина версія WeatherDailyCache (видалено дублікат з weather.py)
# FIX: Додано ForeignKey на weather_zones (був відсутній у цьому файлі)
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, Date, Boolean, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class WeatherDailyCache(Base):
    __tablename__ = "weather_daily_cache"
    __table_args__ = (
        UniqueConstraint("zone_id", "date", name="uq_weather_cache_zone_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # FIX: ForeignKey тепер є (у дублікаті weather.py він БУВ ВІДСУТНІЙ)
    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("weather_zones.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)

    temp_max: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    temp_min: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    temp_avg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    precipitation: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    rain_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    solar_radiation: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    wind_speed: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    humidity_avg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    humidity_max: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    cloud_cover: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    has_dew: Mapped[bool | None] = mapped_column(Boolean)
    is_fog: Mapped[bool | None] = mapped_column(Boolean)
    is_forecast: Mapped[bool] = mapped_column(Boolean, default=False)
    source_api: Mapped[str] = mapped_column(String(50), default="open_meteo")
    # FIX: server_default замість default=datetime.utcnow
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    zone: Mapped["WeatherZone"] = relationship(back_populates="weather_cache")
