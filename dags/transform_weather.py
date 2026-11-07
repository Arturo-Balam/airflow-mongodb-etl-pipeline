"""Transformation logic for dataset 1: Open-Meteo daily weather -> processed_weather.

Standardization: snake_case names with units in the name, ISO 8601 dates, Celsius, mm, km/h.
Cleaning: drops days without a date or temperatures, drops impossible values, removes duplicates.
Enrichment: mean temperature, daily range, heat category, extreme heat and rainy day flags,
weather description.
"""

from __future__ import annotations

from typing import Any

from utils.processing import read_raw, save_processed
from utils.transform_helpers import (
    TransformStats,
    drop_duplicates,
    parse_float,
    parse_iso_date,
    to_celsius,
    to_kmh,
    to_mm,
)

SOURCE = "weather"
PLAUSIBLE_TEMPERATURE_C = (-90.0, 60.0)
EXTREME_HEAT_C = 38.0
RAINY_DAY_MM = 1.0
WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def heat_category(temp_max_c: float) -> str:
    if temp_max_c >= EXTREME_HEAT_C:
        return "extreme"
    if temp_max_c >= 35:
        return "hot"
    if temp_max_c >= 30:
        return "warm"
    return "mild"


def describe_weather_code(code: int | None) -> str:
    if code is None:
        return "unknown"
    return WEATHER_CODES.get(code, "other")


def _value(daily: dict[str, Any], key: str, index: int) -> Any:
    values = daily.get(key) or []
    return values[index] if index < len(values) else None


def transform_weather(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], TransformStats]:
    daily = payload.get("daily") or {}
    units = payload.get("daily_units") or {}
    days = daily.get("time") or []
    stats = TransformStats(records_in=len(days))
    records: list[dict[str, Any]] = []

    for index, day in enumerate(days):
        raw_max = parse_float(_value(daily, "temperature_2m_max", index))
        raw_min = parse_float(_value(daily, "temperature_2m_min", index))
        if day is None or raw_max is None or raw_min is None:
            stats.dropped_missing += 1
            continue
        try:
            date = parse_iso_date(day)
        except (AttributeError, ValueError):
            stats.dropped_corrupted += 1
            continue

        temp_max = to_celsius(raw_max, units.get("temperature_2m_max", "°C"))
        temp_min = to_celsius(raw_min, units.get("temperature_2m_min", "°C"))
        low, high = PLAUSIBLE_TEMPERATURE_C
        if not low <= temp_min <= temp_max <= high:
            stats.dropped_corrupted += 1
            continue

        raw_rain = parse_float(_value(daily, "precipitation_sum", index))
        precipitation_imputed = raw_rain is None
        # No rain value usually means no rain was recorded, so a missing value becomes 0.
        rain = 0.0 if raw_rain is None else to_mm(raw_rain, units.get("precipitation_sum", "mm"))
        raw_wind = parse_float(_value(daily, "wind_speed_10m_max", index))
        wind = (
            None if raw_wind is None else to_kmh(raw_wind, units.get("wind_speed_10m_max", "km/h"))
        )
        raw_code = parse_float(_value(daily, "weather_code", index))
        code = None if raw_code is None else int(raw_code)
        if precipitation_imputed:
            stats.imputed += 1

        records.append(
            {
                "_id": date,
                "date": date,
                "temp_max_c": round(temp_max, 1),
                "temp_min_c": round(temp_min, 1),
                "temp_mean_c": round((temp_max + temp_min) / 2, 1),
                "temp_range_c": round(temp_max - temp_min, 1),
                "precipitation_mm": round(rain, 1),
                "precipitation_imputed": precipitation_imputed,
                "wind_speed_max_kmh": None if wind is None else round(wind, 1),
                "weather_code": code,
                "weather_description": describe_weather_code(code),
                "heat_category": heat_category(temp_max),
                "is_extreme_heat": temp_max >= EXTREME_HEAT_C,
                "is_rainy_day": rain >= RAINY_DAY_MM,
            }
        )

    records, stats.dropped_duplicates = drop_duplicates(records, "date")
    records.sort(key=lambda record: record["date"])
    stats.records_out = len(records)
    return records, stats


def run_transform_weather(ingest_summary: dict[str, Any]) -> dict[str, Any]:
    raw = read_raw(ingest_summary)
    records, stats = transform_weather(raw["payload"])
    return save_processed(SOURCE, records, stats, raw)
