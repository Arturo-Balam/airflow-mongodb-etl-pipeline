"""I/O shared by the transform tasks: read the raw document, write the processed ones."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from utils.mongo_utils import get_document, upsert_documents
from utils.transform_helpers import TransformStats

log = logging.getLogger(__name__)


def read_raw(ingest_summary: dict[str, Any]) -> dict[str, Any]:
    """Load the raw document that the ingestion task reported in its XCom summary."""
    raw = get_document(ingest_summary["collection"], ingest_summary["raw_id"])
    if raw is None:
        raise LookupError(f"{ingest_summary['raw_id']} not found in {ingest_summary['collection']}")
    return raw


def save_processed(
    source: str, records: list[dict[str, Any]], stats: TransformStats, raw: dict[str, Any]
) -> dict[str, Any]:
    """Upsert the cleaned records into processed_<source> and return a summary for XCom.

    Records carry a natural key as _id (a date or an event id), so overlapping windows
    from consecutive runs overwrite the same documents with the freshest data.
    """
    processed_at = datetime.now(timezone.utc)
    for record in records:
        record["raw_id"] = raw["_id"]
        record["processed_at"] = processed_at
    collection = f"processed_{source}"
    upsert_documents(collection, records)
    log.info("%s: %s", collection, stats.as_dict())
    return {"source": source, "collection": collection, "window": raw["window"], **stats.as_dict()}
