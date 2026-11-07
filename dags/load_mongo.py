"""Final task: build the cross-source daily overview, audit the run and clean up old raw data.

- processed_daily_overview: one document per date joining weather, exchange rate and earthquakes.
- pipeline_runs: one audit document per DAG run with the summary of every task.
- Indexes are created if missing, and raw documents older than the retention period are deleted.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.mongo_utils import delete_older_than, ensure_index, find_documents, upsert_documents

log = logging.getLogger(__name__)

RAW_COLLECTIONS = ("raw_weather", "raw_fx", "raw_earthquakes")
RAW_RETENTION_DAYS = 30
INDEXES: list[tuple[str, list[tuple[str, int]]]] = [
    ("processed_weather", [("date", 1)]),
    ("processed_fx", [("date", 1)]),
    ("processed_earthquakes", [("event_date", 1)]),
    ("processed_earthquakes", [("magnitude", -1)]),
    ("pipeline_runs", [("finished_at", -1)]),
    *[(name, [("fetched_at", 1)]) for name in RAW_COLLECTIONS],
]


def _empty_row(date: str) -> dict[str, Any]:
    return {
        "_id": date,
        "date": date,
        "temp_max_c": None,
        "temp_min_c": None,
        "precipitation_mm": None,
        "is_extreme_heat": None,
        "usd_mxn_rate": None,
        "usd_mxn_change_pct": None,
        "earthquake_count": 0,
        "max_magnitude": None,
        "significant_earthquake_count": 0,
    }


def build_daily_overview(
    weather: list[dict[str, Any]], fx: list[dict[str, Any]], earthquakes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join the three processed datasets by date (earthquakes by UTC date). Missing values are
    None, except the earthquake counts, where no event means 0."""
    rows: dict[str, dict[str, Any]] = {}

    def row(date: str) -> dict[str, Any]:
        return rows.setdefault(date, _empty_row(date))

    for doc in weather:
        row(doc["date"]).update(
            temp_max_c=doc["temp_max_c"],
            temp_min_c=doc["temp_min_c"],
            precipitation_mm=doc["precipitation_mm"],
            is_extreme_heat=doc["is_extreme_heat"],
        )
    for doc in fx:
        row(doc["date"]).update(
            usd_mxn_rate=doc["usd_mxn_rate"], usd_mxn_change_pct=doc["usd_mxn_change_pct"]
        )
    for doc in earthquakes:
        target = row(doc["event_date"])
        target["earthquake_count"] += 1
        target["significant_earthquake_count"] += int(doc["is_significant"])
        current = target["max_magnitude"]
        target["max_magnitude"] = (
            doc["magnitude"] if current is None else max(current, doc["magnitude"])
        )
    return [rows[date] for date in sorted(rows)]


def run_load(transform_summaries: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    start = min(summary["window"]["start"] for summary in transform_summaries)
    end = max(summary["window"]["end"] for summary in transform_summaries)

    for collection, keys in INDEXES:
        ensure_index(collection, keys)

    weather = find_documents("processed_weather", {"date": {"$gte": start, "$lte": end}})
    fx = find_documents("processed_fx", {"date": {"$gte": start, "$lte": end}})
    quakes = find_documents("processed_earthquakes", {"event_date": {"$gte": start, "$lte": end}})
    overview = build_daily_overview(weather, fx, quakes)

    now = datetime.now(timezone.utc)
    for row in overview:
        row["updated_at"] = now
    upsert_documents("processed_daily_overview", overview)

    cutoff = now - timedelta(days=RAW_RETENTION_DAYS)
    deleted = {name: delete_older_than(name, "fetched_at", cutoff) for name in RAW_COLLECTIONS}

    summary = {
        "run_id": run_id,
        "window": {"start": start, "end": end},
        "overview_rows": len(overview),
        "raw_deleted": deleted,
    }
    audit = {
        "_id": run_id,
        "finished_at": now,
        "tasks": {item["source"]: item for item in transform_summaries},
        **summary,
    }
    upsert_documents("pipeline_runs", [audit])
    log.info("Load finished: %s", summary)
    return summary
