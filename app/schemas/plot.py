from pydantic import BaseModel, UUID4
from datetime import datetime
from decimal import Decimal


class PlotCreate(BaseModel):
    name: str
    description: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    elevation_m: Decimal | None = None
    area_sqm: Decimal | None = None
    soil_type: str = "loam"
    plot_ph_class: str | None = None
    plot_drainage_class: str | None = None
    plot_organic_input: str | None = None
    plot_last_season_quality: str | None = None
    plot_user_survey: dict | None = None


class PlotUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    elevation_m: Decimal | None = None
    area_sqm: Decimal | None = None
    soil_type: str | None = None
    plot_ph_class: str | None = None
    plot_drainage_class: str | None = None
    plot_organic_input: str | None = None
    plot_last_season_quality: str | None = None
    plot_user_survey: dict | None = None


class PlotResponse(BaseModel):
    id: UUID4
    user_id: UUID4
    zone_id: UUID4 | None
    name: str
    description: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    elevation_m: Decimal | None
    area_sqm: Decimal | None
    soil_type: str = "loam"
    plot_ph_class: str | None = None
    plot_drainage_class: str | None = None
    plot_organic_input: str | None = None
    plot_last_season_quality: str | None = None
    plot_user_survey: dict | None = None
    is_deleted: bool
    updated_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
