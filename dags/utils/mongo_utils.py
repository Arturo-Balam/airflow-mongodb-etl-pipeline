"""MongoDB helpers shared by the pipeline tasks.

Connection settings come from the environment (MONGO_URI and MONGO_DB),
which docker-compose.yml injects into the Airflow containers.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
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


def get_document(collection: str, doc_id: Any) -> dict[str, Any] | None:
    """Return one document by _id, or None if it does not exist."""
    with mongo_db() as db:
        return db[collection].find_one({"_id": doc_id})


def find_documents(
    collection: str,
    query: dict[str, Any] | None = None,
    sort: list[tuple[str, int]] | None = None,
    limit: int = 0,
) -> list[dict[str, Any]]:
    """Return the documents matching a query (all of them when query is None)."""
    with mongo_db() as db:
        cursor = db[collection].find(query or {})
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)


def ensure_index(collection: str, keys: list[tuple[str, int]], unique: bool = False) -> str:
    """Create an index if it does not exist yet (safe to call on every run)."""
    with mongo_db() as db:
        return db[collection].create_index(keys, unique=unique)


def delete_older_than(collection: str, field: str, cutoff: datetime) -> int:
    """Delete documents whose date field is before the cutoff. Returns how many were removed."""
    with mongo_db() as db:
        return db[collection].delete_many({field: {"$lt": cutoff}}).deleted_count
