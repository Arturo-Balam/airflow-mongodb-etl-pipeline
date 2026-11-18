"""Sample frames shaped like the dashboard loaders' output (used by the dashboard tests)."""

from datetime import datetime

import pandas as pd


def sample_overview() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2026-11-01", periods=5),
            "temp_max_c": [33.0, 34.5, 39.0, 36.0, 35.0],
            "temp_min_c": [22.0, 23.0, 24.0, 23.5, 22.5],
            "precipitation_mm": [0.0, 0.0, 1.5, 4.0, 0.0],
            "is_extreme_heat": [False, False, True, False, False],
            "usd_mxn_rate": [18.0, None, 18.2, 18.1, None],  # no rate on weekends
            "usd_mxn_change_pct": [None, None, 0.011, -0.005, None],
            "earthquake_count": [1, 1, 2, 0, 1],
            "max_magnitude": [3.0, 4.2, 6.3, None, 2.6],
            "significant_earthquake_count": [0, 0, 2, 0, 0],
        }
    )


def sample_earthquakes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": ["a", "b", "c", "d", "e"],
            "event_time": pd.to_datetime(
                [
                    "2026-11-01T10:00:00Z",
                    "2026-11-02T11:30:00Z",
                    "2026-11-03T08:15:00Z",
                    "2026-11-03T20:45:00Z",
                    "2026-11-05T01:05:00Z",
                ],
                utc=True,
            ),
            "event_date": pd.to_datetime(
                ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-03", "2026-11-05"]
            ),
            "magnitude": [3.0, 4.2, 5.1, 6.3, 2.6],
            "latitude": [16.8, 17.2, 15.9, 18.0, 19.5],
            "longitude": [-99.1, -100.0, -94.5, -90.5, -97.0],
            "depth_km": [25.0, 10.0, 60.0, 33.0, 5.0],
            "place": ["A, Mexico", "B, Mexico", "C, Mexico", "D, Mexico", "E, Mexico"],
            "magnitude_class": ["minor", "light", "moderate", "strong", "minor"],
            "distance_to_merida_km": [1100.0, 1200.0, 600.0, 230.0, 900.0],
            "is_near_merida": [False, False, True, True, True],
            "is_significant": [False, False, True, True, False],
        }
    )


def sample_run_documents() -> list[dict]:
    def task(out: int, missing: int = 0, corrupted: int = 0) -> dict:
        return {
            "records_out": out,
            "dropped_missing": missing,
            "dropped_corrupted": corrupted,
            "dropped_duplicates": 0,
            "imputed": 1,
        }

    return [
        {
            "_id": "run-2",
            "finished_at": datetime(2026, 11, 7, 8, 5),
            "window": {"start": "2026-11-01", "end": "2026-11-07"},
            "overview_rows": 7,
            "tasks": {
                "weather": task(7),
                "fx": task(5, missing=1),
                "earthquakes": task(3, corrupted=2),
            },
        },
        {
            "_id": "run-1",
            "finished_at": datetime(2026, 11, 6, 8, 5),
            "window": {"start": "2026-10-31", "end": "2026-11-06"},
            "overview_rows": 7,
            "tasks": {"weather": task(7), "fx": task(5), "earthquakes": task(2)},
        },
    ]
