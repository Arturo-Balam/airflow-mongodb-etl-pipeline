"""Reusable, pure helpers for the transformation tasks (no I/O, easy to unit test)."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Any

EARTH_RADIUS_KM = 6371.0088


@dataclass
class TransformStats:
    """Counters that describe what a transformation did. Returned through XCom."""

    records_in: int = 0
    records_out: int = 0
    dropped_missing: int = 0
    dropped_corrupted: int = 0
    dropped_duplicates: int = 0
    imputed: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


def parse_float(value: Any) -> float | None:
    """Convert 18.3, "18.30" or "1,234.5" to a float. Returns None for missing or non numeric
    values such as None, "" or Banxico's "N/E" (no data)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value).strip().replace(",", ""))
        except ValueError:
            return None
    return number if math.isfinite(number) else None


def parse_iso_date(text: str) -> str:
    """Validate a YYYY-MM-DD date and return it in ISO 8601. Raises ValueError otherwise."""
    return date.fromisoformat(text.strip()).isoformat()


def ddmmyyyy_to_iso_date(text: str) -> str:
    """Convert Banxico's DD/MM/YYYY to ISO 8601 (YYYY-MM-DD). Raises ValueError otherwise."""
    return datetime.strptime(text.strip(), "%d/%m/%Y").date().isoformat()


def epoch_ms_to_iso(milliseconds: float) -> str:
    """Convert epoch milliseconds (USGS) to an ISO 8601 UTC timestamp."""
    moment = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def to_celsius(value: float, unit: str) -> float:
    unit = unit.strip()
    if unit in ("°C", "C"):
        return value
    if unit in ("°F", "F"):
        return (value - 32) * 5 / 9
    raise ValueError(f"Unsupported temperature unit: {unit!r}")


def to_kmh(value: float, unit: str) -> float:
    factors = {"km/h": 1.0, "m/s": 3.6, "mp/h": 1.609344, "mph": 1.609344, "kn": 1.852}
    if unit.strip() not in factors:
        raise ValueError(f"Unsupported wind speed unit: {unit!r}")
    return value * factors[unit.strip()]


def to_mm(value: float, unit: str) -> float:
    factors = {"mm": 1.0, "cm": 10.0, "inch": 25.4}
    if unit.strip() not in factors:
        raise ValueError(f"Unsupported precipitation unit: {unit!r}")
    return value * factors[unit.strip()]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def drop_duplicates(
    records: Iterable[dict[str, Any]], key: str
) -> tuple[list[dict[str, Any]], int]:
    """Keep one record per key value, the last one seen (the fresher). Returns (records, count)."""
    unique: dict[Any, dict[str, Any]] = {}
    dropped = 0
    for record in records:
        if record[key] in unique:
            dropped += 1
        unique[record[key]] = record
    return list(unique.values()), dropped
