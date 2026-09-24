"""Tests for MongoDB connection helpers."""

import logging

import pytest

import db.connection as db_conn
from db.connection import redact_mongo_uri


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        (
            "mongodb+srv://alice:s3cr3t@cluster0.abcd.mongodb.net/intelliclaim?retryWrites=true&w=majority",
            "mongodb+srv://***@cluster0.abcd.mongodb.net/intelliclaim",
        ),
        (
            "mongodb://admin:p%40ss@h1:27017,h2:27017/db?replicaSet=rs0",
            "mongodb://***@h1:27017,h2:27017/db",
        ),
        ("mongodb://user@localhost:27017", "mongodb://***@localhost:27017"),
        ("mongodb://localhost:27017", "mongodb://localhost:27017"),
        ("mongodb://localhost:27017/?tlsCertificateKeyFilePassword=secret", "mongodb://localhost:27017/"),
        ("not a uri", "<unparseable MongoDB URI>"),
    ],
)
def test_redact_mongo_uri(uri, expected):
    assert redact_mongo_uri(uri) == expected


async def test_connect_db_never_logs_credentials(monkeypatch, caplog):
    """The startup log line must not contain the password from MONGODB_URI."""
    secret_uri = "mongodb://alice:hunter2@127.0.0.1:1/intelliclaim?authSource=admin"
    monkeypatch.setattr(db_conn.settings, "MONGODB_URI", secret_uri)

    class _FakeAdmin:
        async def command(self, name):
            return {"ok": 1}

    class _FakeClient:
        def __init__(self, uri, **kwargs):
            self.admin = _FakeAdmin()

        def __getitem__(self, name):
            return object()

        def close(self):
            pass

    async def _no_indexes():
        return None

    monkeypatch.setattr(db_conn, "AsyncIOMotorClient", _FakeClient)
    monkeypatch.setattr(db_conn, "_create_indexes", _no_indexes)
    original_client, original_db = db_conn._client, db_conn._database

    with caplog.at_level(logging.INFO, logger="db.connection"):
        await db_conn.connect_db()

    db_conn._client, db_conn._database = original_client, original_db
    assert "hunter2" not in caplog.text
    assert "alice" not in caplog.text
    assert "mongodb://***@127.0.0.1:1/intelliclaim" in caplog.text
