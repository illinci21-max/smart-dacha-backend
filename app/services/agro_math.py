"""Shared agronomic math helpers for engine and batch services."""
from __future__ import annotations


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
