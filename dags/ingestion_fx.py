"""Ingestion logic for API 2: Banxico SIE, USD/MXN FIX exchange rate (series SF43718).

Docs: https://www.banxico.org.mx/SieAPIRest/service/v1/
Free token: https://www.banxico.org.mx/SieAPIRest/service/v1/token
"""

from __future__ import annotations

import os
from typing import Any

from utils.api_helpers import Window, fetch_json, store_raw

SOURCE = "fx"
SERIES_ID = "SF43718"
BASE_URL = "https://www.banxico.org.mx/SieAPIRest/service/v1/series"


def build_url(window: Window) -> str:
    return f"{BASE_URL}/{SERIES_ID}/datos/{window.start.isoformat()}/{window.end.isoformat()}"


def count_records(payload: dict[str, Any]) -> int:
    """One record per published day (Banxico publishes business days only)."""
    series = payload.get("bmx", {}).get("series", [])
    return len(series[0].get("datos", [])) if series else 0


def ingest_fx(window: Window) -> dict[str, Any]:
    token = os.environ.get("BANXICO_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BANXICO_TOKEN is not set. Add it to .env, then run: docker compose up -d"
        )
    url = build_url(window)
    # The token goes in a header, so it never appears in the URL, the logs or the stored request.
    payload = fetch_json(url, headers={"Bmx-Token": token, "Accept": "application/json"})
    return store_raw(
        SOURCE, window, {"url": url, "series": SERIES_ID}, payload, count_records(payload)
    )
