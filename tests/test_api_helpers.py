"""Unit tests for utils.api_helpers (no network and no MongoDB)."""

from datetime import date, datetime, timezone

import pytest
import requests

from utils import api_helpers
from utils.api_helpers import Window, build_window, fetch_json, store_raw


class FakeResponse:
    def __init__(self, status_code=200, body=None, text="", url="https://api.test/x"):
        self.status_code = status_code
        self._body = body
        self.text = text
        self.url = url

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body


def test_build_window_ends_on_the_interval_day_and_looks_back():
    start = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)

    window = build_window(start, lookback_days=7)

    assert window == Window(start=date(2026, 10, 30), end=date(2026, 11, 5))


def test_build_window_with_one_day_is_a_single_day():
    start = datetime(2026, 11, 5, 8, 0, tzinfo=timezone.utc)

    assert build_window(start, lookback_days=1) == Window(date(2026, 11, 5), date(2026, 11, 5))


def test_build_window_rejects_zero_lookback():
    with pytest.raises(ValueError):
        build_window(datetime(2026, 11, 5, tzinfo=timezone.utc), lookback_days=0)


def test_store_raw_builds_a_deterministic_id_and_returns_a_summary(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        api_helpers, "upsert_documents", lambda name, docs: saved.update(name=name, docs=docs)
    )
    window = Window(date(2026, 10, 30), date(2026, 11, 5))

    summary = store_raw("weather", window, {"url": "https://x"}, {"daily": {}}, 7)

    doc = saved["docs"][0]
    assert saved["name"] == "raw_weather"
    assert doc["_id"] == "weather:2026-10-30:2026-11-05"
    assert doc["payload"] == {"daily": {}}
    assert doc["record_count"] == 7
    assert doc["window"] == {"start": "2026-10-30", "end": "2026-11-05"}
    assert doc["fetched_at"].tzinfo is not None
    assert summary == {
        "source": "weather",
        "collection": "raw_weather",
        "record_count": 7,
        "window": {"start": "2026-10-30", "end": "2026-11-05"},
    }


def test_fetch_json_returns_the_parsed_body(monkeypatch):
    monkeypatch.setattr(
        requests.Session, "get", lambda self, *a, **k: FakeResponse(body={"ok": True})
    )

    assert fetch_json("https://api.test/x") == {"ok": True}


def test_fetch_json_keeps_the_api_error_message(monkeypatch):
    bad = FakeResponse(status_code=400, text='{"reason": "Invalid daily variable"}')
    monkeypatch.setattr(requests.Session, "get", lambda self, *a, **k: bad)

    with pytest.raises(requests.HTTPError, match="Invalid daily variable"):
        fetch_json("https://api.test/x")
