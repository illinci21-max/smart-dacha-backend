import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TreatmentApplication(Base):
    """Structured fertilizer/protection application journal.

    GardenAction remains the generic "work was done" event used by the engine.
    This table stores agronomic details needed for nutrient budget, PHI/REI and
    resistance-management checks.
    """

    __tablename__ = "treatment_applications"
    __table_args__ = (
        Index("ix_treatment_plot_applied", "plot_id", text("applied_at DESC")),
        Index("ix_treatment_user_kind", "user_id", "treatment_kind"),
        Index("ix_treatment_action", "garden_action_id"),
        Index("ix_treatment_work_plan", "work_plan_item_id"),
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
    garden_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("garden_actions.id", ondelete="SET NULL")
    )
    work_plan_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_plan_items.id", ondelete="SET NULL")
    )

    treatment_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="work_plan", server_default="work_plan")

    plant_type: Mapped[str | None] = mapped_column(String(100))
    variety: Mapped[str | None] = mapped_column(String(100))
    cell_col: Mapped[int | None] = mapped_column(Integer)
    cell_row: Mapped[int | None] = mapped_column(Integer)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="single", server_default="single")

    product_profile_id: Mapped[str | None] = mapped_column(String(80))
    product_name: Mapped[str | None] = mapped_column(String(160))
    product_type: Mapped[str | None] = mapped_column(String(80))
    application_method: Mapped[str | None] = mapped_column(String(80))
    target_problem: Mapped[str | None] = mapped_column(String(120))
    frac_group: Mapped[str | None] = mapped_column(String(30))

    n_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    p_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    k_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    mg_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    ca_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))

    reentry_days: Mapped[int | None] = mapped_column(Integer)
    pre_harvest_interval_days: Mapped[int | None] = mapped_column(Integer)
    rainfast_hours: Mapped[int | None] = mapped_column(Integer)

    rate_amount: Mapped[str | None] = mapped_column(String(120))
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    applied_amount: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    reasons: Mapped[list | None] = mapped_column(JSONB)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    garden_action: Mapped["GardenAction | None"] = relationship()
    work_plan_item: Mapped["WorkPlanItem | None"] = relationship()
