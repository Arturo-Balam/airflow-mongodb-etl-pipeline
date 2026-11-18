"""MongoDB queries for the dashboard. Each loader returns a DataFrame cached for 60 seconds,
so the page follows the pipeline closely without querying MongoDB on every click."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd
import streamlit as st
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

CACHE_SECONDS = 60
SOURCES = ("weather", "fx", "earthquakes")
DROP_COUNTERS = ("dropped_missing", "dropped_corrupted", "dropped_duplicates")


@st.cache_resource
def get_db() -> Database:
    client = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=5000)
    return client[os.environ["MONGO_DB"]]


def check_connection() -> str | None:
    """Return None when MongoDB answers, otherwise the error text."""
    try:
        get_db().command("ping")
    except PyMongoError as exc:
        return str(exc)
    return None


def _frame(collection: str, hidden_fields: dict[str, int]) -> pd.DataFrame:
    return pd.DataFrame(list(get_db()[collection].find({}, {"_id": 0, **hidden_fields})))


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_overview() -> pd.DataFrame:
    """One row per date joining weather, exchange rate and earthquakes."""
    frame = _frame("processed_daily_overview", {"updated_at": 0})
    if frame.empty:
        return frame
    frame["date"] = pd.to_datetime(frame["date"])
    return frame.sort_values("date").reset_index(drop=True)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_earthquakes() -> pd.DataFrame:
    frame = _frame("processed_earthquakes", {"raw_id": 0, "processed_at": 0})
    if frame.empty:
        return frame
    frame["event_time"] = pd.to_datetime(frame["event_time"], utc=True)
    frame["event_date"] = pd.to_datetime(frame["event_date"])
    return frame.sort_values("event_time").reset_index(drop=True)


def flatten_runs(documents: list[dict[str, Any]]) -> pd.DataFrame:
    """Turn pipeline_runs documents into one flat row per run (newest order is kept)."""
    rows = []
    for doc in documents:
        window = doc.get("window") or {}
        row: dict[str, Any] = {
            "run_id": doc["_id"],
            "finished_at": doc.get("finished_at"),
            "window_start": window.get("start"),
            "window_end": window.get("end"),
            "overview_rows": doc.get("overview_rows"),
        }
        for source in SOURCES:
            task = (doc.get("tasks") or {}).get(source) or {}
            row[f"{source}_out"] = task.get("records_out")
            row[f"{source}_dropped"] = sum(task.get(key) or 0 for key in DROP_COUNTERS)
            row[f"{source}_imputed"] = task.get("imputed")
        rows.append(row)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["finished_at"] = pd.to_datetime(frame["finished_at"], utc=True)
    return frame


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def load_runs(limit: int = 20) -> pd.DataFrame:
    cursor = get_db()["pipeline_runs"].find({}).sort("finished_at", -1).limit(limit)
    return flatten_runs(list(cursor))


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def collection_counts() -> pd.DataFrame:
    db = get_db()
    names = sorted(db.list_collection_names())
    return pd.DataFrame(
        {"collection": names, "documents": [db[name].count_documents({}) for name in names]}
    )
