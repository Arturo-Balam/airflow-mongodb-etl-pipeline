"""Smoke test: checks that Airflow can reach MongoDB with the credentials from .env.

Trigger it once after `docker compose up`. A green run means the Airflow to
MongoDB path works; it also shows a first XCom (the boolean passed between tasks).
"""

from __future__ import annotations

from datetime import datetime, timezone

from airflow.decorators import dag, task

from utils.mongo_utils import mongo_db, ping, upsert_documents


@dag(
    dag_id="smoke_test_mongo",
    schedule=None,
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    tags=["smoke"],
    doc_md=__doc__,
)
def smoke_test_mongo():
    @task
    def check_connection() -> bool:
        if not ping():
            raise RuntimeError("MongoDB did not answer the ping.")
        return True

    @task
    def write_and_read(connected: bool) -> int:
        stamp = {"_id": "smoke", "checked_at": datetime.now(timezone.utc).isoformat()}
        upsert_documents("smoke_test", [stamp])
        with mongo_db() as db:
            return db["smoke_test"].count_documents({})

    write_and_read(check_connection())


smoke_test_mongo()
