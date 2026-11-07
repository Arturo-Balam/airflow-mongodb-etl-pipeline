"""Tiny in-memory stand-in for the mongo_utils functions, used by the pipeline flow tests."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any


class FakeStore:
    def __init__(self) -> None:
        self.collections: dict[str, dict[Any, dict[str, Any]]] = {}
        self.indexes: list[tuple[str, list[tuple[str, int]]]] = []

    def upsert_documents(self, collection: str, documents: list[dict[str, Any]]) -> int:
        target = self.collections.setdefault(collection, {})
        for document in documents:
            target[document["_id"]] = copy.deepcopy(document)
        return len(documents)

    def get_document(self, collection: str, doc_id: Any) -> dict[str, Any] | None:
        return copy.deepcopy(self.collections.get(collection, {}).get(doc_id))

    def find_documents(
        self,
        collection: str,
        query: dict[str, Any] | None = None,
        sort: list[tuple[str, int]] | None = None,
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        docs = [
            copy.deepcopy(doc)
            for doc in self.collections.get(collection, {}).values()
            if self._matches(doc, query or {})
        ]
        for field, direction in reversed(sort or []):
            docs.sort(key=lambda doc: doc[field], reverse=direction < 0)
        return docs[:limit] if limit else docs

    def ensure_index(self, collection: str, keys: list[tuple[str, int]], unique: bool = False):
        self.indexes.append((collection, keys))
        return "index"

    def delete_older_than(self, collection: str, field: str, cutoff: datetime) -> int:
        target = self.collections.get(collection, {})
        old = [key for key, doc in target.items() if doc[field] < cutoff]
        for key in old:
            del target[key]
        return len(old)

    @staticmethod
    def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for field, condition in query.items():
            value = doc.get(field)
            if not isinstance(condition, dict):
                if value != condition:
                    return False
                continue
            checks = {
                "$gte": lambda v, c: v >= c,
                "$gt": lambda v, c: v > c,
                "$lte": lambda v, c: v <= c,
                "$lt": lambda v, c: v < c,
            }
            for operator, bound in condition.items():
                if value is None or not checks[operator](value, bound):
                    return False
        return True
