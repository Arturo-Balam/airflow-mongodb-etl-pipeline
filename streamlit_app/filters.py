"""Filtering and summary helpers for the dashboard (pure functions on DataFrames)."""

from __future__ import annotations

from datetime import date

import pandas as pd


def filter_overview(overview: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    if overview.empty:
        return overview
    mask = (overview["date"] >= pd.Timestamp(start)) & (overview["date"] <= pd.Timestamp(end))
    return overview.loc[mask]


def filter_earthquakes(
    quakes: pd.DataFrame, start: date, end: date, min_magnitude: float, near_only: bool
) -> pd.DataFrame:
    if quakes.empty:
        return quakes
    mask = (
        (quakes["event_date"] >= pd.Timestamp(start))
        & (quakes["event_date"] <= pd.Timestamp(end))
        & (quakes["magnitude"] >= min_magnitude)
    )
    if near_only:
        mask &= quakes["is_near_merida"].astype(bool)
    return quakes.loc[mask]


def latest_with_delta(frame: pd.DataFrame, column: str) -> tuple[float | None, float | None]:
    """Latest non-empty value of a column and its change from the previous non-empty value."""
    if frame.empty or column not in frame:
        return None, None
    values = frame.sort_values("date")[column].dropna()
    if values.empty:
        return None, None
    latest = float(values.iloc[-1])
    delta = float(latest - values.iloc[-2]) if len(values) > 1 else None
    return latest, delta


def count_true(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame:
        return 0
    return int(frame[column].fillna(False).astype(bool).sum())


def top_quakes(quakes: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """The n strongest events, with readable column names for display."""
    strongest = quakes.sort_values("magnitude", ascending=False).head(n)
    return pd.DataFrame(
        {
            "Time (UTC)": strongest["event_time"].dt.strftime("%Y-%m-%d %H:%M"),
            "Magnitude": strongest["magnitude"],
            "Place": strongest["place"],
            "Depth (km)": strongest["depth_km"],
            "Distance to Mérida (km)": strongest["distance_to_merida_km"],
        }
    )
