"""Geocoding via OpenStreetMap Nominatim (free, no API key).

Every lookup is cached in Redis for 30 days: geocoding results for a given
query string are effectively static, and caching keeps API responses fast
while staying well inside Nominatim's fair-use policy.
"""
import hashlib
import logging

import requests
from django.conf import settings
from django.core.cache import cache

from trips.exceptions import GeocodingError

logger = logging.getLogger(__name__)

GEOCODE_TTL = 60 * 60 * 24 * 30  # 30 days
SUGGEST_TTL = 60 * 60 * 24 * 7  # 7 days
REQUEST_TIMEOUT = 10

# FMCSA HOS is a North-American domain: constrain results to the road
# network a US property carrier can actually reach.
COUNTRY_CODES = "us,ca,mx"


def _cache_key(prefix: str, query: str) -> str:
    digest = hashlib.md5(query.strip().lower().encode()).hexdigest()
    return f"{prefix}:{digest}"


def _nominatim_get(path: str, params: dict) -> list:
    try:
        response = requests.get(
            f"{settings.NOMINATIM_BASE_URL}{path}",
            params=params,
            headers={"User-Agent": settings.GEOCODER_USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.warning("Nominatim request failed: %s", exc)
        raise GeocodingError(
            "The geocoding service is temporarily unavailable. Please try again.",
            status_code=502,
        ) from exc


def geocode(query: str) -> dict:
    """Resolve a free-text location to {name, lat, lon}."""
    key = _cache_key("geo2", query)
    cached = cache.get(key)
    if cached:
        return cached

    results = _nominatim_get(
        "/search",
        {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 0,
            "countrycodes": COUNTRY_CODES,
        },
    )
    if not results:
        raise GeocodingError(f'Could not find a location matching "{query}".')

    top = results[0]
    resolved = {
        "query": query,
        "name": top.get("display_name", query),
        "lat": float(top["lat"]),
        "lon": float(top["lon"]),
    }
    cache.set(key, resolved, GEOCODE_TTL)
    return resolved


def suggest(query: str, limit: int = 5) -> list:
    """Return lightweight autocomplete suggestions for a partial query."""
    if len(query.strip()) < 3:
        return []

    key = _cache_key(f"sug2-{limit}", query)
    cached = cache.get(key)
    if cached is not None:
        return cached

    results = _nominatim_get(
        "/search",
        {
            "q": query,
            "format": "json",
            "limit": limit,
            "addressdetails": 0,
            "countrycodes": COUNTRY_CODES,
        },
    )
    suggestions = [
        {
            "name": item.get("display_name", ""),
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
        }
        for item in results
    ]
    cache.set(key, suggestions, SUGGEST_TTL)
    return suggestions
