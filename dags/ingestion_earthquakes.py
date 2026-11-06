"""Ingestion logic for API 3: USGS earthquakes inside a bounding box around Mexico.

Docs: https://earthquake.usgs.gov/fdsnws/event/1/ (no API key, public domain).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from utils.api_helpers import Window, fetch_json, store_raw

SOURCE = "earthquakes"
URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
BOUNDING_BOX = {
    "minlatitude": 14.0,
    "maxlatitude": 33.0,
    "minlongitude": -119.0,
    "maxlongitude": -86.0,
}
MIN_MAGNITUDE = 2.5


def build_params(window: Window) -> dict[str, Any]:
    return {
        "format": "geojson",
        "eventtype": "earthquake",
        "starttime": window.start.isoformat(),
        # USGS reads a bare end date as 00:00 UTC, so add a day to include the last one.
        "endtime": (window.end + timedelta(days=1)).isoformat(),
        "minmagnitude": MIN_MAGNITUDE,
        "orderby": "time-asc",
        "limit": 20000,
        **BOUNDING_BOX,
    }


def count_records(payload: dict[str, Any]) -> int:
    """One record per earthquake (GeoJSON feature)."""
    return len(payload.get("features", []))


def ingest_earthquakes(window: Window) -> dict[str, Any]:
    params = build_params(window)
    payload = fetch_json(URL, params=params)
    return store_raw(
        SOURCE, window, {"url": URL, "params": params}, payload, count_records(payload)
    )
