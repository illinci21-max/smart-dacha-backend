from __future__ import annotations

from app.models.garden_observation import GardenObservation


def observation_to_engine_payload(observation: GardenObservation) -> dict:
    return {
        "id": str(observation.id),
        "scope": observation.scope,
        "plant_type": observation.plant_type,
        "variety": observation.variety,
        "cell_col": observation.cell_col,
        "cell_row": observation.cell_row,
        "soil_moisture_pct": observation.soil_moisture_pct,
        "soil_moisture_status": observation.soil_moisture_status,
        "leaf_condition": observation.leaf_condition,
        "symptoms": observation.symptoms or [],
        "growth_phase": observation.growth_phase,
        "species_filter": observation.species_filter or None,
        "observed_perennial_season": observation.observed_perennial_season,
        "notes": observation.notes,
        "observed_at": observation.observed_at,
    }
