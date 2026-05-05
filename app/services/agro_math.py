"""Shared agronomic math helpers for engine and batch services."""
from __future__ import annotations

from datetime import date


def calculate_gdd_delta(
    temp_min: float,
    temp_max: float,
    t_base: float,
    t_upper: float | None = None,
) -> float:
    upper = t_upper if t_upper is not None and t_upper > t_base else None
    capped_min = min(temp_min, upper) if upper is not None else temp_min
    capped_max = min(temp_max, upper) if upper is not None else temp_max
    return max(0.0, ((capped_max + capped_min) / 2.0) - t_base)


def _snapshot_date(snapshot: object) -> date | None:
    snap_date = getattr(snapshot, "date", None)
    if snap_date is None:
        return None
    if isinstance(snap_date, str):
        try:
            return date.fromisoformat(snap_date[:10])
        except ValueError:
            return None
    return snap_date


def cumulative_gdd_calendar_year(
    weather_history: list,
    today: date,
    t_base: float,
    t_upper: float | None = None,
) -> float:
    """Sum GDD from January 1 of the current year up to today.

    For perennial plants, phenological stages are anchored to calendar time
    (winter chill -> spring warming), not to planting date.
    """
    year_start = date(today.year, 1, 1)
    total = 0.0

    for snapshot in weather_history:
        snap_date = _snapshot_date(snapshot)
        if snap_date is None or snap_date < year_start or snap_date > today:
            continue
        total += calculate_gdd_delta(
            snapshot.temp_min,
            snapshot.temp_max,
            t_base,
            t_upper,
        )

    return total


def cumulative_gdd_from_planting(
    weather_history: list,
    planted_date: date,
    today: date,
    t_base: float,
    t_upper: float | None = None,
) -> float:
    """Sum GDD from planted_date up to today for annual plants."""
    total = 0.0

    for snapshot in weather_history:
        snap_date = _snapshot_date(snapshot)
        if snap_date is None or snap_date < planted_date or snap_date > today:
            continue
        total += calculate_gdd_delta(
            snapshot.temp_min,
            snapshot.temp_max,
            t_base,
            t_upper,
        )

    return total
