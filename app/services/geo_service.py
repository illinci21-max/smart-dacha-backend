"""
GeoService — geographic calculations for garden plots.

Provides:
  - Haversine-based area calculation from polygon points
  - Bounding-box dimensions (width × height in meters)
  - Automatic grid scale suggestion based on plot area
  - GPS permission wrapper (Flet / platform-agnostic)

All calculations use the Haversine formula for short distances
(< 10 km), which is accurate to < 0.1% for typical garden plots.
"""
from __future__ import annotations

import logging
import math
from typing import Sequence

from app.models.plot_types import (
    GeoJSONPolygon,
    GridConfig,
    GridScale,
    LatLng,
)

logger = logging.getLogger(__name__)

# Earth mean radius in meters (WGS-84)
_EARTH_R_M = 6_371_000.0


# ── Haversine helpers ─────────────────────────────────────────────────────────

def haversine_distance_m(a: LatLng, b: LatLng) -> float:
    """Return the great-circle distance in meters between two points."""
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlng = math.radians(b.lng - a.lng)

    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return 2 * _EARTH_R_M * math.asin(math.sqrt(h))


def polygon_area_sqm(points: Sequence[LatLng]) -> float:
    """
    Compute the approximate area of a polygon in square meters using the
    Spherical Excess formula (suitable for small polygons < 100 km²).

    Points must be ordered (CW or CCW); the ring need NOT be closed.
    Returns 0.0 for degenerate inputs (< 3 points).
    """
    n = len(points)
    if n < 3:
        return 0.0

    total = 0.0
    for i in range(n):
        p1 = points[i]
        p2 = points[(i + 1) % n]
        # Convert to radians
        lat1, lat2 = math.radians(p1.lat), math.radians(p2.lat)
        lng1, lng2 = math.radians(p1.lng), math.radians(p2.lng)
        total += (lng2 - lng1) * (2 + math.sin(lat1) + math.sin(lat2))

    area = abs(total) * (_EARTH_R_M ** 2) / 2
    return round(area, 2)


def bounding_box_dimensions_m(points: Sequence[LatLng]) -> tuple[float, float]:
    """
    Return the approximate (width_m, height_m) of the bounding box
    that encloses the given polygon points.
    Width  = E–W extent (longitude span).
    Height = N–S extent (latitude span).
    """
    if not points:
        return 0.0, 0.0

    min_lat = min(p.lat for p in points)
    max_lat = max(p.lat for p in points)
    min_lng = min(p.lng for p in points)
    max_lng = max(p.lng for p in points)

    center_lat = (min_lat + max_lat) / 2
    ref = LatLng(center_lat, min_lng)

    height_m = haversine_distance_m(
        LatLng(min_lat, min_lng), LatLng(max_lat, min_lng)
    )
    width_m = haversine_distance_m(
        LatLng(center_lat, min_lng), LatLng(center_lat, max_lng)
    )
    return round(width_m, 2), round(height_m, 2)


# ── GeoJSON helpers ───────────────────────────────────────────────────────────

def latlng_list_to_geojson(points: Sequence[LatLng]) -> GeoJSONPolygon:
    """
    Convert an ordered list of LatLng points into a GeoJSON Polygon.
    Automatically closes the ring (first == last).
    GeoJSON uses [longitude, latitude] order.
    """
    coords = [[p.lng, p.lat] for p in points]
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])  # close the ring
    return {"type": "Polygon", "coordinates": [coords]}


def geojson_to_latlng_list(polygon: GeoJSONPolygon) -> list[LatLng]:
    """
    Extract the exterior ring from a GeoJSON Polygon as LatLng list.
    The closing duplicate point is stripped.
    """
    ring = polygon.get("coordinates", [[]])[0]
    points = [LatLng(lat=c[1], lng=c[0]) for c in ring]
    # Drop closing duplicate
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    return points


def polygon_centroid(points: Sequence[LatLng]) -> LatLng | None:
    """Return the arithmetic centroid of the polygon (for map centering)."""
    if not points:
        return None
    return LatLng(
        lat=sum(p.lat for p in points) / len(points),
        lng=sum(p.lng for p in points) / len(points),
    )


# ── Grid suggestion ───────────────────────────────────────────────────────────

# Thresholds (m²) → suggested cell size
_SCALE_THRESHOLDS: list[tuple[float, GridScale]] = [
    (25,   GridScale.FINE),      # < 25 m²  → 0.25 m cells
    (200,  GridScale.STANDARD),  # < 200 m² → 0.5 m cells
    (1000, GridScale.NORMAL),    # < 1000 m² → 1 m cells
]
_DEFAULT_SCALE = GridScale.COARSE

# Maximum grid dimension in one axis (safety cap)
_MAX_GRID_DIM = 200


def suggest_grid_scale(area_sqm: float) -> GridScale:
    """Return the most appropriate GridScale for a given plot area."""
    for threshold, scale in _SCALE_THRESHOLDS:
        if area_sqm < threshold:
            return scale
    return _DEFAULT_SCALE


def build_grid_config(
    width_m: float,
    height_m: float,
    area_sqm: float,
    cell_size_override: float | None = None,
) -> GridConfig:
    """
    Build a GridConfig from plot dimensions.

    Args:
        width_m: E–W extent of the plot in meters.
        height_m: N–S extent of the plot in meters.
        area_sqm: Calculated polygon area in m².
        cell_size_override: If provided, use this cell size instead of auto.

    Returns:
        GridConfig with cols, rows, cell size, and area.
    """
    if cell_size_override is not None:
        cell_size = max(0.1, cell_size_override)
    else:
        scale = suggest_grid_scale(area_sqm)
        cell_size = scale.value

    cols = max(1, min(_MAX_GRID_DIM, round(width_m / cell_size)))
    rows = max(1, min(_MAX_GRID_DIM, round(height_m / cell_size)))

    logger.debug(
        "GridConfig: %dx%d cells @ %.2fm, area=%.1fm²",
        cols, rows, cell_size, area_sqm,
    )

    return GridConfig(
        cols=cols,
        rows=rows,
        cell_size_m=cell_size,
        width_m=round(width_m, 1),
        height_m=round(height_m, 1),
        area_sqm=area_sqm,
    )


def compute_plot_geometry(
    points: Sequence[LatLng],
    cell_size_override: float | None = None,
) -> tuple[float, float, float, GridConfig]:
    """
    One-shot helper: given polygon points, return
    (width_m, height_m, area_sqm, grid_config).
    """
    area = polygon_area_sqm(points)
    width, height = bounding_box_dimensions_m(points)
    grid = build_grid_config(width, height, area, cell_size_override)
    return width, height, area, grid


# ── Geolocation ───────────────────────────────────────────────────────────────

class GeoLocationError(Exception):
    """Raised when geolocation is unavailable or permission is denied."""

    class Reason:
        PERMISSION_DENIED  = "permission_denied"
        UNAVAILABLE        = "unavailable"
        TIMEOUT            = "timeout"
        UNKNOWN            = "unknown"

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


async def request_current_location() -> LatLng:
    """
    Request the device's current GPS location.

    On desktop/web this falls back to a configurable default coordinate
    (Kyiv, Ukraine) when native geolocation is unavailable.

    Raises:
        GeoLocationError: If location cannot be obtained.
    """
    # Flet does not yet expose a native geolocation API on all platforms.
    # When running as a web app, JS geolocation is available via page.run_javascript.
    # For desktop / mobile builds, integrate platform-specific plugins here.
    #
    # This stub returns a sensible Ukrainian default so the map can open
    # immediately. In production, replace with actual platform API call.
    logger.warning(
        "GeoService.request_current_location: "
        "native GPS not yet wired — returning default Kyiv coordinates."
    )
    return LatLng(lat=50.4501, lng=30.5234)   # Kyiv


def format_coordinates(point: LatLng, decimal_places: int = 5) -> str:
    """Return a human-readable coordinate string."""
    fmt = f"{{:.{decimal_places}f}}"
    ns = "N" if point.lat >= 0 else "S"
    ew = "E" if point.lng >= 0 else "W"
    return f"{fmt.format(abs(point.lat))}°{ns}, {fmt.format(abs(point.lng))}°{ew}"


def format_area(area_sqm: float) -> str:
    """Return a human-friendly area string (m² or ha)."""
    if area_sqm >= 10_000:
        return f"{area_sqm / 10_000:.2f} га"
    return f"{area_sqm:.0f} м²"
