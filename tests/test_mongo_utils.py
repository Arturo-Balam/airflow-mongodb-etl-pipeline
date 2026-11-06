"""Unit tests for utils.mongo_utils (no MongoDB needed, the database is stubbed)."""

from contextlib import contextmanager

from pymongo import ReplaceOne

from utils import mongo_utils


class FakeResult:
    upserted_count = 1
    modified_count = 1
    matched_count = 2


class FakeCollection:
    def __init__(self):
        self.operations = None

    def bulk_write(self, operations, ordered):
        self.operations = operations
        return FakeResult()


def fake_db_factory(collection):
    @contextmanager
    def fake_mongo_db():
        yield {"things": collection}

    return fake_mongo_db


def test_upsert_documents_replaces_by_id_with_upsert(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(mongo_utils, "mongo_db", fake_db_factory(collection))
    docs = [{"_id": "a", "value": 1}, {"_id": "b", "value": 2}]

    written = mongo_utils.upsert_documents("things", docs)

    assert written == 2
    assert collection.operations == [
        ReplaceOne({"_id": "a"}, docs[0], upsert=True),
        ReplaceOne({"_id": "b"}, docs[1], upsert=True),
    ]


def test_upsert_documents_with_no_documents_never_touches_the_database(monkeypatch):
    def explode():
        raise AssertionError("mongo_db should not be called for an empty list")

    monkeypatch.setattr(mongo_utils, "mongo_db", explode)

    assert mongo_utils.upsert_documents("things", []) == 0
