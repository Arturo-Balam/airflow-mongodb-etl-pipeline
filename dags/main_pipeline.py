"""Batch ETL pipeline: public APIs to MongoDB.

ingest_* (3 tasks, in parallel): save each API response untouched in raw_<source>.
transform_* (3 tasks): clean, standardize and enrich the raw data into processed_<source>.
load: build the daily overview, write the run audit and clean up old raw data.

Each task passes a small summary to the next one through XCom (never the data itself).
Schedule: daily at 08:00 UTC (02:00 in Merida). Each run fetches its own day plus a few
days of lookback, and re-running a day replaces its documents (idempotent).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from airflow.decorators import dag, task
from ingestion_earthquakes import ingest_earthquakes
from ingestion_fx import ingest_fx
from ingestion_weather import ingest_weather
from load_mongo import run_load
from transform_earthquakes import run_transform_earthquakes
from transform_fx import run_transform_fx
from transform_weather import run_transform_weather

from utils.api_helpers import build_window


@dag(
    dag_id="main_pipeline",
    schedule="0 8 * * *",
    start_date=datetime(2026, 11, 1, tzinfo=timezone.utc),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
    tags=["etl"],
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

    @task(task_id="transform_weather", multiple_outputs=False)
    def transform_weather_task(ingest_summary: dict[str, Any]) -> dict[str, Any]:
        return run_transform_weather(ingest_summary)

    @task(task_id="transform_fx", multiple_outputs=False)
    def transform_fx_task(ingest_summary: dict[str, Any]) -> dict[str, Any]:
        return run_transform_fx(ingest_summary)

    @task(task_id="transform_earthquakes", multiple_outputs=False)
    def transform_earthquakes_task(ingest_summary: dict[str, Any]) -> dict[str, Any]:
        return run_transform_earthquakes(ingest_summary)

    @task(task_id="load", multiple_outputs=False)
    def load_task(
        weather: dict[str, Any], fx: dict[str, Any], earthquakes: dict[str, Any], run_id=None
    ) -> dict[str, Any]:
        return run_load([weather, fx, earthquakes], run_id)

    # Passing each summary to the next task is what creates the dependencies:
    # ingest_x >> transform_x for every source, then all three transforms >> load.
    load_task(
        transform_weather_task(ingest_weather_task()),
        transform_fx_task(ingest_fx_task()),
        transform_earthquakes_task(ingest_earthquakes_task()),
    )


main_pipeline()
