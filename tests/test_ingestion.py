"""Unit tests for the three ingestion modules (API calls and MongoDB are stubbed)."""

from datetime import date

import ingestion_earthquakes
import ingestion_fx
import ingestion_weather
import pytest

from utils import api_helpers
from utils.api_helpers import Window

WINDOW = Window(date(2026, 10, 30), date(2026, 11, 5))


@pytest.fixture
def saved(monkeypatch):
    """Capture what would be written to MongoDB."""
    store = {}
    monkeypatch.setattr(
        api_helpers, "upsert_documents", lambda name, docs: store.update(name=name, docs=docs)
    )
    return store


def test_weather_params_cover_the_window_in_merida_time():
    params = ingestion_weather.build_params(WINDOW)

    assert params["start_date"] == "2026-10-30"
    assert params["end_date"] == "2026-11-05"
    assert params["timezone"] == "America/Merida"
    assert "temperature_2m_max" in params["daily"].split(",")


def test_weather_ingest_stores_one_record_per_day(monkeypatch, saved):
    payload = {"daily": {"time": ["2026-11-04", "2026-11-05"], "temperature_2m_max": [33.1, 32.4]}}
    monkeypatch.setattr(ingestion_weather, "fetch_json", lambda url, params=None: payload)

    summary = ingestion_weather.ingest_weather(WINDOW)

    assert summary["record_count"] == 2
    assert saved["name"] == "raw_weather"
    assert saved["docs"][0]["payload"] == payload


def test_fx_url_uses_the_fix_series_and_iso_dates():
    assert ingestion_fx.build_url(WINDOW).endswith("/series/SF43718/datos/2026-10-30/2026-11-05")


def test_fx_count_handles_empty_and_missing_series():
    assert ingestion_fx.count_records({"bmx": {"series": [{"datos": [{}, {}]}]}}) == 2
    assert ingestion_fx.count_records({"bmx": {"series": [{"idSerie": "SF43718"}]}}) == 0
    assert ingestion_fx.count_records({}) == 0


def test_fx_requires_a_token(monkeypatch):
    monkeypatch.delenv("BANXICO_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="BANXICO_TOKEN"):
        ingestion_fx.ingest_fx(WINDOW)


def test_fx_sends_the_token_in_a_header_and_never_stores_it(monkeypatch, saved):
    monkeypatch.setenv("BANXICO_TOKEN", "secret-token-123")
    calls = {}

    def fake_fetch(url, params=None, headers=None):
        calls["headers"] = headers
        return {"bmx": {"series": [{"datos": [{"fecha": "05/11/2026", "dato": "18.3"}]}]}}

    monkeypatch.setattr(ingestion_fx, "fetch_json", fake_fetch)

    summary = ingestion_fx.ingest_fx(WINDOW)

    assert calls["headers"]["Bmx-Token"] == "secret-token-123"
    assert summary["record_count"] == 1
    assert "secret-token-123" not in str(saved["docs"])


def test_earthquake_params_include_the_last_day_and_the_bounding_box():
    params = ingestion_earthquakes.build_params(WINDOW)

    assert params["starttime"] == "2026-10-30"
    assert params["endtime"] == "2026-11-06"
    assert params["format"] == "geojson"
    assert params["minlatitude"] < params["maxlatitude"]
    assert params["minlongitude"] < params["maxlongitude"]


def test_earthquake_ingest_counts_features(monkeypatch, saved):
    payload = {"features": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    monkeypatch.setattr(ingestion_earthquakes, "fetch_json", lambda url, params=None: payload)

    summary = ingestion_earthquakes.ingest_earthquakes(WINDOW)

    assert summary["record_count"] == 3
    assert saved["name"] == "raw_earthquakes"
