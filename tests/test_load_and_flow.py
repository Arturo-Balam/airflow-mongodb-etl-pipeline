"""Tests for the load step and for the whole ingest, transform and load flow.

MongoDB and the three APIs are replaced by an in-memory store and canned responses.
"""

from datetime import date, datetime, timedelta, timezone

import ingestion_earthquakes
import ingestion_fx
import ingestion_weather
import load_mongo
import pytest
import transform_earthquakes
import transform_fx
import transform_weather
from fake_store import FakeStore

from utils import api_helpers, processing
from utils.api_helpers import Window


def quake_ms(day: str, hour: int = 12) -> int:
    moment = datetime.fromisoformat(day).replace(hour=hour, tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def quake(event_id, day, mag):
    return {
        "id": event_id,
        "properties": {"mag": mag, "time": quake_ms(day), "place": "Somewhere, Mexico"},
        "geometry": {"coordinates": [-99.0, 17.0, 20.0]},
    }


# ------------------------------------------------------------------------ overview join


def test_daily_overview_joins_the_three_datasets_by_date():
    weather = [
        {"date": "2026-11-04", "temp_max_c": 33.0, "temp_min_c": 22.0, "precipitation_mm": 0.0,
         "is_extreme_heat": False},
        {"date": "2026-11-07", "temp_max_c": 39.0, "temp_min_c": 24.0, "precipitation_mm": 2.0,
         "is_extreme_heat": True},
    ]  # fmt: skip
    fx = [{"date": "2026-11-04", "usd_mxn_rate": 18.1, "usd_mxn_change_pct": 0.01}]
    quakes = [
        {"event_date": "2026-11-04", "magnitude": 4.2, "is_significant": False},
        {"event_date": "2026-11-04", "magnitude": 5.4, "is_significant": True},
        {"event_date": "2026-11-05", "magnitude": 3.0, "is_significant": False},
    ]

    rows = load_mongo.build_daily_overview(weather, fx, quakes)

    assert [r["date"] for r in rows] == ["2026-11-04", "2026-11-05", "2026-11-07"]
    first, only_quake, only_weather = rows
    assert first["usd_mxn_rate"] == 18.1
    assert first["earthquake_count"] == 2
    assert first["max_magnitude"] == 5.4
    assert first["significant_earthquake_count"] == 1
    assert only_quake["temp_max_c"] is None
    assert only_quake["usd_mxn_rate"] is None
    assert only_quake["earthquake_count"] == 1
    assert only_weather["earthquake_count"] == 0
    assert only_weather["max_magnitude"] is None
    assert only_weather["is_extreme_heat"] is True


# ------------------------------------------------------------------------ full flow


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(api_helpers, "upsert_documents", fake.upsert_documents)
    monkeypatch.setattr(processing, "upsert_documents", fake.upsert_documents)
    monkeypatch.setattr(processing, "get_document", fake.get_document)
    monkeypatch.setattr(transform_fx, "find_documents", fake.find_documents)
    for name in ("find_documents", "upsert_documents", "ensure_index", "delete_older_than"):
        monkeypatch.setattr(load_mongo, name, getattr(fake, name))
    monkeypatch.setenv("BANXICO_TOKEN", "test-token")
    return fake


def run_pipeline(monkeypatch, window, fx_rows, run_id="run-1"):
    days = [
        (window.start + timedelta(days=i)).isoformat()
        for i in range((window.end - window.start).days + 1)
    ]
    weather = {
        "daily_units": {"temperature_2m_max": "°C", "temperature_2m_min": "°C"},
        "daily": {
            "time": days,
            "temperature_2m_max": [33.0 + i for i in range(len(days))],
            "temperature_2m_min": [22.0] * len(days),
        },
    }
    quakes = {"features": [quake("q1", days[0], 4.5), quake("q2", days[0], 5.2)]}
    monkeypatch.setattr(ingestion_weather, "fetch_json", lambda url, params=None: weather)
    monkeypatch.setattr(
        ingestion_fx,
        "fetch_json",
        lambda url, headers=None: {"bmx": {"series": [{"datos": fx_rows}]}},
    )
    monkeypatch.setattr(ingestion_earthquakes, "fetch_json", lambda url, params=None: quakes)

    raw = [
        ingestion_weather.ingest_weather(window),
        ingestion_fx.ingest_fx(window),
        ingestion_earthquakes.ingest_earthquakes(window),
    ]
    clean = [
        transform_weather.run_transform_weather(raw[0]),
        transform_fx.run_transform_fx(raw[1]),
        transform_earthquakes.run_transform_earthquakes(raw[2]),
    ]
    return raw, clean, load_mongo.run_load(clean, run_id)


FX_NOV_3_TO_5 = [
    {"fecha": "03/11/2026", "dato": "18.00"},
    {"fecha": "04/11/2026", "dato": "18.10"},
    {"fecha": "05/11/2026", "dato": "18.40"},
]


def test_flow_writes_raw_processed_overview_and_audit(monkeypatch, store):
    window = Window(date(2026, 11, 3), date(2026, 11, 5))

    raw, clean, loaded = run_pipeline(monkeypatch, window, FX_NOV_3_TO_5)

    assert raw[0]["raw_id"] == "weather:2026-11-03:2026-11-05"
    assert set(store.collections["raw_fx"]) == {"fx:2026-11-03:2026-11-05"}
    assert sorted(store.collections["processed_weather"]) == [
        "2026-11-03",
        "2026-11-04",
        "2026-11-05",
    ]
    assert sorted(store.collections["processed_fx"]) == ["2026-11-03", "2026-11-04", "2026-11-05"]
    assert sorted(store.collections["processed_earthquakes"]) == ["q1", "q2"]
    assert [c["records_out"] for c in clean] == [3, 3, 2]
    assert loaded["overview_rows"] == 3

    overview = store.collections["processed_daily_overview"]
    assert overview["2026-11-03"]["earthquake_count"] == 2
    assert overview["2026-11-03"]["significant_earthquake_count"] == 1
    assert overview["2026-11-04"]["usd_mxn_rate"] == 18.1
    audit = store.collections["pipeline_runs"]["run-1"]
    assert set(audit["tasks"]) == {"weather", "fx", "earthquakes"}
    assert ("processed_fx", [("date", 1)]) in store.indexes


def test_rerunning_the_same_window_does_not_duplicate_anything(monkeypatch, store):
    window = Window(date(2026, 11, 3), date(2026, 11, 5))

    run_pipeline(monkeypatch, window, FX_NOV_3_TO_5)
    sizes = {name: len(docs) for name, docs in store.collections.items()}
    run_pipeline(monkeypatch, window, FX_NOV_3_TO_5)

    assert {name: len(docs) for name, docs in store.collections.items()} == sizes


def test_overlapping_windows_keep_the_fx_change_of_the_first_day(monkeypatch, store):
    run_pipeline(monkeypatch, Window(date(2026, 11, 3), date(2026, 11, 5)), FX_NOV_3_TO_5)
    next_rows = FX_NOV_3_TO_5[1:] + [{"fecha": "06/11/2026", "dato": "18.50"}]

    run_pipeline(monkeypatch, Window(date(2026, 11, 4), date(2026, 11, 6)), next_rows, "run-2")

    fx = store.collections["processed_fx"]
    # 2026-11-04 is the first day of the second window, but its change still uses 11-03 from run 1
    assert fx["2026-11-04"]["usd_mxn_change"] == 0.1
    assert fx["2026-11-06"]["usd_mxn_change"] == 0.1
    assert sorted(store.collections["pipeline_runs"]) == ["run-1", "run-2"]


def test_load_deletes_raw_documents_older_than_the_retention_period(monkeypatch, store):
    old = datetime.now(timezone.utc) - timedelta(days=load_mongo.RAW_RETENTION_DAYS + 5)
    store.upsert_documents("raw_fx", [{"_id": "fx:old", "fetched_at": old}])

    _, _, loaded = run_pipeline(
        monkeypatch, Window(date(2026, 11, 3), date(2026, 11, 5)), FX_NOV_3_TO_5
    )

    assert loaded["raw_deleted"]["raw_fx"] == 1
    assert "fx:old" not in store.collections["raw_fx"]
    assert "fx:2026-11-03:2026-11-05" in store.collections["raw_fx"]


def test_transform_fails_clearly_when_the_raw_document_is_missing(store):
    summary = {"collection": "raw_fx", "raw_id": "fx:missing"}

    with pytest.raises(LookupError, match="fx:missing"):
        transform_fx.run_transform_fx(summary)
