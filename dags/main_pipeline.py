"""Batch ETL pipeline: public APIs to MongoDB.

Current stage: three ingestion tasks, one per API, each saving the untouched response
in its own raw_<source> collection. Every task returns a small summary (record count
and fetched window) through XCom. Transform and load tasks come next.

Schedule: daily at 08:00 UTC (02:00 in Merida). Each run fetches its own day plus a
few days of lookback, and re-running a day replaces its documents (idempotent).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from airflow.decorators import dag, task
from ingestion_earthquakes import ingest_earthquakes
from ingestion_fx import ingest_fx
from ingestion_weather import ingest_weather

from utils.api_helpers import build_window


@dag(
    dag_id="main_pipeline",
    schedule="0 8 * * *",
    start_date=datetime(2026, 11, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
    tags=["etl", "ingestion"],
    doc_md=__doc__,
)
def main_pipeline():
    @task(task_id="ingest_weather", multiple_outputs=False)
    def ingest_weather_task(data_interval_start=None) -> dict[str, Any]:
        return ingest_weather(build_window(data_interval_start))

    @task(task_id="ingest_fx", multiple_outputs=False)
    def ingest_fx_task(data_interval_start=None) -> dict[str, Any]:
        return ingest_fx(build_window(data_interval_start))

    @task(task_id="ingest_earthquakes", multiple_outputs=False)
    def ingest_earthquakes_task(data_interval_start=None) -> dict[str, Any]:
        return ingest_earthquakes(build_window(data_interval_start))

    ingest_weather_task()
    ingest_fx_task()
    ingest_earthquakes_task()


main_pipeline()
