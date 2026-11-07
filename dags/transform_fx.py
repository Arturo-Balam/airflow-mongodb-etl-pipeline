"""Transformation logic for dataset 2: Banxico USD/MXN FIX rate -> processed_fx.

Standardization: snake_case names, DD/MM/YYYY converted to ISO 8601, rates as floats,
percentage changes as decimals (0.0123 means 1.23%).
Cleaning: drops days without a rate ("N/E"), drops impossible rates, removes duplicates.
Enrichment: daily change, daily change as a decimal, peso trend, large move flag.
"""

from __future__ import annotations

from typing import Any

from utils.mongo_utils import find_documents
from utils.processing import read_raw, save_processed
from utils.transform_helpers import (
    TransformStats,
    ddmmyyyy_to_iso_date,
    drop_duplicates,
    parse_float,
)

SOURCE = "fx"
PLAUSIBLE_RATE_MXN_PER_USD = (1.0, 100.0)
LARGE_MOVE = 0.01  # a change of 1% or more in one business day


def transform_fx(
    payload: dict[str, Any], previous_rate: float | None = None
) -> tuple[list[dict[str, Any]], TransformStats]:
    """Clean the Banxico series. previous_rate is the last stored rate before this window,
    used to compute the change for the first day."""
    series = (payload.get("bmx") or {}).get("series") or []
    rows = (series[0].get("datos") if series else None) or []
    stats = TransformStats(records_in=len(rows))
    records: list[dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            stats.dropped_corrupted += 1
            continue
        rate = parse_float(row.get("dato"))
        raw_date = row.get("fecha")
        if rate is None or not raw_date:
            stats.dropped_missing += 1
            continue
        try:
            date = ddmmyyyy_to_iso_date(raw_date)
        except ValueError:
            stats.dropped_corrupted += 1
            continue
        low, high = PLAUSIBLE_RATE_MXN_PER_USD
        if not low <= rate <= high:
            stats.dropped_corrupted += 1
            continue
        records.append({"_id": date, "date": date, "usd_mxn_rate": round(rate, 4)})

    records, stats.dropped_duplicates = drop_duplicates(records, "date")
    records.sort(key=lambda record: record["date"])

    previous = previous_rate
    for record in records:
        rate = record["usd_mxn_rate"]
        if previous is None:
            change = change_pct = trend = None
            large_move = False
        else:
            change = round(rate - previous, 4)
            change_pct = round(rate / previous - 1, 6)
            # More pesos per dollar means the peso lost value.
            trend = "weakening" if change > 0 else "strengthening" if change < 0 else "stable"
            large_move = abs(change_pct) >= LARGE_MOVE
        record.update(
            usd_mxn_change=change,
            usd_mxn_change_pct=change_pct,
            peso_trend=trend,
            is_large_move=large_move,
        )
        previous = rate

    stats.records_out = len(records)
    return records, stats


def run_transform_fx(ingest_summary: dict[str, Any]) -> dict[str, Any]:
    raw = read_raw(ingest_summary)
    earlier = find_documents(
        "processed_fx",
        {"date": {"$lt": raw["window"]["start"]}},
        sort=[("date", -1)],
        limit=1,
    )
    previous_rate = earlier[0]["usd_mxn_rate"] if earlier else None
    records, stats = transform_fx(raw["payload"], previous_rate)
    return save_processed(SOURCE, records, stats, raw)
