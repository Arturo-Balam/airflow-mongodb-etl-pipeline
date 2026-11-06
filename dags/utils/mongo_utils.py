"""MongoDB helpers shared by the pipeline tasks.

Connection settings come from the environment (MONGO_URI and MONGO_DB),
which docker-compose.yml injects into the Airflow containers.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from pymongo import MongoClient, ReplaceOne
from pymongo.database import Database

log = logging.getLogger(__name__)


@contextmanager
def mongo_db() -> Iterator[Database]:
    """Yield the pipeline database and close the client when the block ends.

    A client per call keeps tasks safe under Airflow's forked task processes.
    """
    client = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=5000, tz_aware=True)
    try:
        yield client[os.environ["MONGO_DB"]]
    finally:
        client.close()


def ping() -> bool:
    """Return True if MongoDB answers with the configured credentials."""
    with mongo_db() as db:
        return db.command("ping").get("ok") == 1.0


def upsert_documents(collection: str, documents: list[dict[str, Any]]) -> int:
    """Insert or replace documents by _id, so re-running a task never duplicates data.

    Every document must carry a deterministic _id. Returns the number of
    documents written (0 for an empty list).
    """
    if not documents:
        log.info("upsert_documents(%s): nothing to write", collection)
        return 0

    operations = [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in documents]
    with mongo_db() as db:
        result = db[collection].bulk_write(operations, ordered=False)

    log.info(
        "upsert_documents(%s): %d new, %d changed, %d unchanged",
        collection,
        result.upserted_count,
        result.modified_count,
        result.matched_count - result.modified_count,
    )
    return len(documents)
