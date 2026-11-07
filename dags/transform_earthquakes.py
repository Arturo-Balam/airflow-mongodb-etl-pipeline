"""Transformation logic for dataset 3: USGS earthquakes -> processed_earthquakes.

Standardization: flat snake_case records, epoch milliseconds converted to ISO 8601 UTC,
GeoJSON [lon, lat, depth] unpacked into named fields.
Cleaning: drops events without id, magnitude, time or position, drops impossible values,
removes duplicates.
Enrichment: magnitude class, depth class, distance to Merida, near Merida and significant flags.
"""

from __future__ import annotations

from typing import Any

from utils.processing import read_raw, save_processed
from utils.transform_helpers import (
    TransformStats,
    drop_duplicates,
    epoch_ms_to_iso,
    haversine_km,
    parse_float,
)

SOURCE = "earthquakes"
MERIDA = (20.9674, -89.5926)
NEAR_MERIDA_KM = 1000.0
SIGNIFICANT_MAGNITUDE = 5.0


def magnitude_class(magnitude: float) -> str:
    if magnitude >= 7:
        return "major"
    if magnitude >= 6:
        return "strong"
    if magnitude >= 5:
        return "moderate"
    if magnitude >= 4:
        return "light"
    return "minor"


def depth_class(depth_km: float | None) -> str:
    if depth_km is None:
        return "unknown"
    if depth_km < 70:
        return "shallow"
    if depth_km <= 300:
        return "intermediate"
    return "deep"


def transform_earthquakes(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], TransformStats]:
    features = payload.get("features") or []
    stats = TransformStats(records_in=len(features))
    records: list[dict[str, Any]] = []

    for feature in features:
        if not isinstance(feature, dict):
            stats.dropped_corrupted += 1
            continue
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        event_id = feature.get("id")
        magnitude = parse_float(props.get("mag"))
        time_ms = parse_float(props.get("time"))
        longitude = parse_float(coords[0]) if len(coords) > 0 else None
        latitude = parse_float(coords[1]) if len(coords) > 1 else None
        depth = parse_float(coords[2]) if len(coords) > 2 else None
        if not event_id or None in (magnitude, time_ms, longitude, latitude):
            stats.dropped_missing += 1
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180 and -2 <= magnitude <= 10):
            stats.dropped_corrupted += 1
            continue

        event_time = epoch_ms_to_iso(time_ms)
        felt = parse_float(props.get("felt"))
        # Non critical gaps: no felt reports means 0, no alert means "none".
        imputed = felt is None or props.get("alert") is None or props.get("place") is None
        if imputed:
            stats.imputed += 1
        sig = parse_float(props.get("sig"))
        distance = haversine_km(latitude, longitude, *MERIDA)

        records.append(
            {
                "_id": event_id,
                "event_id": event_id,
                "event_time": event_time,
                "event_date": event_time[:10],
                "magnitude": round(magnitude, 1),
                "magnitude_type": props.get("magType"),
                "place": props.get("place") or "unknown place",
                "latitude": round(latitude, 4),
                "longitude": round(longitude, 4),
                "depth_km": None if depth is None else round(depth, 1),
                "felt_reports": 0 if felt is None else int(felt),
                "alert_level": props.get("alert") or "none",
                "tsunami": bool(props.get("tsunami")),
                "significance": None if sig is None else int(sig),
                "review_status": props.get("status"),
                "url": props.get("url"),
                "magnitude_class": magnitude_class(magnitude),
                "depth_class": depth_class(depth),
                "distance_to_merida_km": round(distance, 1),
                "is_near_merida": distance <= NEAR_MERIDA_KM,
                "is_significant": magnitude >= SIGNIFICANT_MAGNITUDE or bool(props.get("tsunami")),
            }
        )

    records, stats.dropped_duplicates = drop_duplicates(records, "event_id")
    records.sort(key=lambda record: record["event_time"])
    stats.records_out = len(records)
    return records, stats


def run_transform_earthquakes(ingest_summary: dict[str, Any]) -> dict[str, Any]:
    raw = read_raw(ingest_summary)
    records, stats = transform_earthquakes(raw["payload"])
    return save_processed(SOURCE, records, stats, raw)
