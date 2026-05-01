import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, SmallInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100))
    firebase_token: Mapped[str | None] = mapped_column(String(1000))

    # SaaS
    subscription_tier: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free",
        comment="free | premium | premium_plus"
    )
    subscription_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), unique=True)

    plots_limit: Mapped[int] = mapped_column(SmallInteger, default=1)
    plants_limit: Mapped[int] = mapped_column(SmallInteger, default=10)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    plots: Mapped[list["Plot"]] = relationship(back_populates="user", lazy="select")
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", lazy="select"
    )
    finance_transactions: Mapped[list["FinanceTransaction"]] = relationship(
        back_populates="user", lazy="select"
    )
    garden_actions: Mapped[list["GardenAction"]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )
    garden_observations: Mapped[list["GardenObservation"]] = relationship(
        back_populates="user", lazy="select", cascade="all, delete-orphan"
    )

