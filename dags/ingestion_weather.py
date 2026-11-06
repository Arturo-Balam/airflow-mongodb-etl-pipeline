"""Ingestion logic for API 1: Open-Meteo daily weather for Merida, Yucatan.

Docs: https://open-meteo.com/en/docs (no API key, data under CC BY 4.0).
"""

from __future__ import annotations

from typing import Any

from utils.api_helpers import Window, fetch_json, store_raw

SOURCE = "weather"
URL = "https://api.open-meteo.com/v1/forecast"
LATITUDE = 20.9674
LONGITUDE = -89.5926
TIMEZONE = "America/Merida"
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_speed_10m_max",
    "weather_code",
]


def build_params(window: Window) -> dict[str, Any]:
    return {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": TIMEZONE,
        "start_date": window.start.isoformat(),
        "end_date": window.end.isoformat(),
    }


def count_records(payload: dict[str, Any]) -> int:
    """One record per day in the response."""
    return len(payload.get("daily", {}).get("time", []))


def ingest_weather(window: Window) -> dict[str, Any]:
    params = build_params(window)
    payload = fetch_json(URL, params=params)
    return store_raw(
        SOURCE, window, {"url": URL, "params": params}, payload, count_records(payload)
    )
