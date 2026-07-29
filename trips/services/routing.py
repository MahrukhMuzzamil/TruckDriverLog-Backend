"""Road routing via the OSRM public API (free, no API key).

Routes are cached in Redis for 7 days keyed by the rounded coordinates of
the waypoints, so repeated trips between the same places never leave the
cache.
"""
import logging
import math

import requests
from django.conf import settings
from django.core.cache import cache

from trips.exceptions import RoutingError

logger = logging.getLogger(__name__)

ROUTE_TTL = 60 * 60 * 24 * 7  # 7 days
REQUEST_TIMEOUT = 20
METERS_PER_MILE = 1609.344

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(a: list, b: list) -> float:
    """Great-circle distance between two [lat, lon] points, in miles."""
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def get_route(waypoints: list) -> dict:
    """Route through [ {lat, lon}, ... ] waypoints.

    Returns:
        {
          "distance_miles": float,
          "duration_hours": float,          # OSRM car estimate (informational)
          "geometry": [[lat, lon], ...],    # full route polyline
          "legs": [{"distance_miles": ..., "duration_hours": ...}, ...],
          "cumulative_miles": [...],        # distance along geometry per vertex
        }
    """
    key = "route:" + "|".join(f"{p['lat']:.4f},{p['lon']:.4f}" for p in waypoints)
    cached = cache.get(key)
    if cached:
        return cached

    coords = ";".join(f"{p['lon']},{p['lat']}" for p in waypoints)
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coords}"
    try:
        response = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson", "steps": "false"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("OSRM request failed: %s", exc)
        raise RoutingError(
            "The routing service is temporarily unavailable. Please try again."
        ) from exc

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code >= 500:
        raise RoutingError(
            "The routing service is temporarily unavailable. Please try again."
        )

    # OSRM reports unroutable pairs via `code` (NoRoute/NoSegment/...) —
    # that's a problem with the chosen locations, not with the service.
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(
            "No drivable road route exists between those locations. "
            "Double-check each location (all must be reachable by truck "
            "within North America).",
            status_code=400,
        )

    route = data["routes"][0]
    # GeoJSON is [lon, lat]; flip to [lat, lon] for Leaflet friendliness.
    geometry = [[point[1], point[0]] for point in route["geometry"]["coordinates"]]

    cumulative = [0.0]
    for i in range(1, len(geometry)):
        cumulative.append(cumulative[-1] + haversine_miles(geometry[i - 1], geometry[i]))

    result = {
        "distance_miles": route["distance"] / METERS_PER_MILE,
        "duration_hours": route["duration"] / 3600.0,
        "geometry": geometry,
        "legs": [
            {
                "distance_miles": leg["distance"] / METERS_PER_MILE,
                "duration_hours": leg["duration"] / 3600.0,
            }
            for leg in route["legs"]
        ],
        "cumulative_miles": cumulative,
    }
    cache.set(key, result, ROUTE_TTL)
    return result


def point_at_mile(route: dict, mile: float) -> list:
    """Interpolate the [lat, lon] point at a given odometer mile on the route."""
    cumulative = route["cumulative_miles"]
    geometry = route["geometry"]
    if mile <= 0:
        return geometry[0]
    if mile >= cumulative[-1]:
        return geometry[-1]

    # Binary search for the segment containing `mile`.
    lo, hi = 0, len(cumulative) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if cumulative[mid] < mile:
            lo = mid + 1
        else:
            hi = mid
    i = max(1, lo)
    span = cumulative[i] - cumulative[i - 1] or 1e-9
    t = (mile - cumulative[i - 1]) / span
    lat = geometry[i - 1][0] + (geometry[i][0] - geometry[i - 1][0]) * t
    lon = geometry[i - 1][1] + (geometry[i][1] - geometry[i - 1][1]) * t
    return [lat, lon]
