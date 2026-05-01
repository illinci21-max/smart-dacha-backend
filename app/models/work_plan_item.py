import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WorkPlanItem(Base):
    __tablename__ = "work_plan_items"
    __table_args__ = (
        UniqueConstraint("plot_id", "user_id", "recommendation_key", name="uq_work_plan_recommendation"),
        Index("ix_work_plan_plot_status_due", "plot_id", "status", "due_date"),
        Index("ix_work_plan_user_status", "user_id", "status"),
        Index("ix_work_plan_created", text("created_at DESC")),
        Index("ix_work_plan_snoozed_until", "snoozed_until"),
        Index("ix_work_plan_suppressed_until", "suppressed_until"),
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
    recommendation_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="agro_analysis", server_default="agro_analysis")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned", server_default="planned")

    task_type: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", server_default="medium")
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="general", server_default="general")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[str | None] = mapped_column(String(120))
    due_date: Mapped[date | None] = mapped_column(Date)

    plant_type: Mapped[str | None] = mapped_column(String(100))
    variety: Mapped[str | None] = mapped_column(String(100))
    cell_col: Mapped[int | None] = mapped_column(Integer)
    cell_row: Mapped[int | None] = mapped_column(Integer)

    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=80, server_default="80")
    recommendation_type: Mapped[str | None] = mapped_column(String(120))
    reasons: Mapped[list | None] = mapped_column(JSONB)
    reason_groups: Mapped[dict | None] = mapped_column(JSONB)
    constraints: Mapped[list | None] = mapped_column(JSONB)
    blocked_reasons: Mapped[list | None] = mapped_column(JSONB)
    is_hidden: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")

    completed_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("garden_actions.id", ondelete="SET NULL")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suppressed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    plot: Mapped["Plot"] = relationship()
    completed_action: Mapped["GardenAction | None"] = relationship()
