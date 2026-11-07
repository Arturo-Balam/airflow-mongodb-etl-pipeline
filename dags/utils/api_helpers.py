"""HTTP and raw-storage helpers shared by the ingestion tasks."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utils.mongo_utils import upsert_documents

log = logging.getLogger(__name__)

# How many days each run fetches, ending on the day the run covers. The overlap between
# consecutive runs re-fetches recent days, which picks up late or revised data.
LOOKBACK_DAYS = int(os.environ.get("PIPELINE_LOOKBACK_DAYS", "7"))
REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = "airflow-mongodb-etl-pipeline (https://github.com/Arturo-Balam)"


@dataclass(frozen=True)
class Window:
    """Inclusive range of calendar days fetched by one pipeline run."""

    start: date
    end: date

    def as_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


def build_window(data_interval_start: datetime, lookback_days: int = LOOKBACK_DAYS) -> Window:
    """Return the window a run fetches: the run's own day plus the lookback days before it.

    The DAG runs at 08:00 UTC (02:00 in Merida), so the day that just ended is complete in
    both UTC and Merida local time.
    """
    if lookback_days < 1:
        raise ValueError("lookback_days must be at least 1")
    end = data_interval_start.date()
    return Window(start=end - timedelta(days=lookback_days - 1), end=end)


def _session() -> requests.Session:
    """Session that retries transient failures (rate limits and 5xx) with backoff."""
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = USER_AGENT
    return session


def fetch_json(
    url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
) -> Any:
    """GET a JSON document. On an HTTP error the API's own message is kept in the exception."""
    with _session() as session:
        response = session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    if not response.ok:
        raise requests.HTTPError(
            f"{response.status_code} from {response.url}: {response.text[:300]}",
            response=response,
        )
    return response.json()


def store_raw(
    source: str, window: Window, request: dict[str, Any], payload: Any, record_count: int
) -> dict[str, Any]:
    """Save an API response untouched in raw_<source> and return a small summary for XCom.

    The _id is built from the source and the window, so re-running the same window
    replaces the document instead of adding a second one (idempotent). Never put
    secrets in `request`: it is stored in MongoDB.
    """
    collection = f"raw_{source}"
    document = {
        "_id": f"{source}:{window.start.isoformat()}:{window.end.isoformat()}",
        "source": source,
        "fetched_at": datetime.now(timezone.utc),
        "window": window.as_dict(),
        "request": request,
        "record_count": record_count,
        "payload": payload,
    }
    upsert_documents(collection, [document])
    log.info(
        "Stored %d records from %s in %s (window %s to %s)",
        record_count,
        source,
        collection,
        window.start,
        window.end,
    )
    return {
        "source": source,
        "collection": collection,
        "raw_id": document["_id"],
        "record_count": record_count,
        "window": window.as_dict(),
    }
