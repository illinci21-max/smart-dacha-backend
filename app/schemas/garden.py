"""
Garden Planner Schemas — Pydantic v2 моделі для API грядки.

Зміни відносно попередньої версії:
  - GardenCellData: додано category
  - GardenGridSave: додано custom_plants
  - GardenGridResponse: додано custom_plants
  - GardenTaskResponseItem: FAO-56 based (priority, category, description, amount)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, UUID4, Field


class GardenCellData(BaseModel):
    """Одна зайнята клітинка на грядці."""
    col: int
    row: int
    plant_id: UUID4 | None = None
    plant_type: str
    plant_icon: str | None = None
    plant_emoji: str | None = None
    planted_date: str | None = None
    variety: str | None = None
    category: str | None = None


class GardenGridSave(BaseModel):
    """Запит на збереження грядки (PUT)."""
    cols: int = Field(ge=1, le=50, default=15)
    rows: int = Field(ge=1, le=50, default=12)
    cells: list[GardenCellData] = []
    custom_plants: dict[str, Any] | None = None


class GardenGridResponse(BaseModel):
    """Відповідь з збереженою грядкою (GET/PUT)."""
    plot_id: UUID4
    cols: int
    rows: int
    cells: list[GardenCellData]
    custom_plants: dict[str, Any] | None = None
    updated_at: datetime | None = None


class GardenTaskResponseItem(BaseModel):
    """Одне FAO-56 завдання з пріоритетом та деталями."""
    plant_type: str
    plant_icon: str = ""
    planted_date: str = ""
    task_date: str = ""
    action: str
    priority: str = "medium"        # critical | high | medium | low
    category: str = "general"       # watering | fertilizing | protection | harvest | general
    description: str = ""
    amount: str = ""
    confidence: int = 80
    reasons: list[str] = Field(default_factory=list)
    reason_groups: dict[str, list[str]] = Field(default_factory=dict)
    recommendation_type: str = ""
    constraints: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    is_hidden: bool = False
    task_type: str = "general"
    title: str = ""
    plant_name: str = ""
    variety: str = ""
    cell_col: int = -1
    cell_row: int = -1
    due_date: str = ""


class GardenTasksResponse(BaseModel):
    """Усі завдання для грядки."""
    plot_id: UUID4
    tasks: list[GardenTaskResponseItem]
    hidden_tasks: list[GardenTaskResponseItem] = Field(default_factory=list)
    status: str = "ready"
    retry_after: int | None = None
    weather_status: str | None = None

class GardenObservationCreate(BaseModel):
    scope: str = "plot"
    plant_type: str | None = None
    variety: str | None = None
    cell_col: int | None = None
    cell_row: int | None = None
    soil_moisture_pct: int | None = Field(default=None, ge=0, le=100)
    soil_moisture_status: str | None = None
    leaf_condition: str | None = None
    symptoms: list[str] = Field(default_factory=list)
    growth_phase: str | None = None
    notes: str | None = None
    observed_at: datetime | None = None


class GardenObservationResponse(GardenObservationCreate):
    id: str
    plot_id: UUID4
    created_at: datetime

class GardenActionCreate(BaseModel):
    """Виконана робота з Плану робіт."""
    action_type: str
    plant_type: str | None = None
    variety: str | None = None
    cell_col: int | None = None
    cell_row: int | None = None
    amount: str | None = None
    notes: str | None = None
    task_title: str | None = None
    scope: str = "single"


class GardenActionResponse(GardenActionCreate):
    """Збережена виконана робота."""
    id: str
    created_at: datetime


class WorkPlanItemResponse(BaseModel):
    id: str
    plot_id: UUID4
    recommendation_key: str
    source: str = "agro_analysis"
    status: str = "planned"
    task_type: str = "general"
    priority: str = "medium"
    category: str = "general"
    title: str
    description: str = ""
    amount: str = ""
    due_date: str | None = None
    plant_type: str | None = None
    variety: str | None = None
    cell_col: int | None = None
    cell_row: int | None = None
    confidence: int = 80
    recommendation_type: str = ""
    reasons: list[str] = Field(default_factory=list)
    reason_groups: dict[str, list[str]] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    is_hidden: bool = False
    completed_action_id: str | None = None
    completed_at: datetime | None = None
    snoozed_until: datetime | None = None
    suppressed_until: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkPlanItemUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None
    snoozed_until: datetime | None = None


class WorkPlanCompleteAction(BaseModel):
    amount: str | None = None
    notes: str | None = None
    scope: str | None = None


class TreatmentApplicationCreate(BaseModel):
    treatment_kind: str
    plant_type: str | None = None
    variety: str | None = None
    cell_col: int | None = None
    cell_row: int | None = None
    scope: str = "single"
    product_profile_id: str | None = None
    product_name: str | None = None
    product_type: str | None = None
    application_method: str | None = None
    target_problem: str | None = None
    frac_group: str | None = None
    n_pct: float | None = None
    p_pct: float | None = None
    k_pct: float | None = None
    mg_pct: float | None = None
    ca_pct: float | None = None
    reentry_days: int | None = None
    pre_harvest_interval_days: int | None = None
    rainfast_hours: int | None = None
    rate_amount: str | None = None
    area_sqm: float | None = None
    applied_amount: str | None = None
    notes: str | None = None
    reasons: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class TreatmentApplicationResponse(TreatmentApplicationCreate):
    id: str
    plot_id: UUID4
    garden_action_id: str | None = None
    work_plan_item_id: str | None = None
    source: str = "work_plan"
    applied_at: datetime
    created_at: datetime

