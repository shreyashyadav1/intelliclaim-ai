"""Tests for the demo data seeder (the database write itself is not exercised)."""

import random
from datetime import UTC, datetime

import pytest

from seed_data import SEED, build_demo_data, is_local_database

NOW = datetime(2026, 9, 1, 12, tzinfo=UTC)


def test_seeded_generation_is_reproducible():
    assert build_demo_data(random.Random(SEED), NOW) == build_demo_data(random.Random(SEED), NOW)


def test_generated_claims_and_documents_are_consistent():
    claims, documents = build_demo_data(random.Random(SEED), NOW)
    claim_ids = {claim["_id"] for claim in claims}

    assert len(claims) == 50
    assert len({claim["claim_number"] for claim in claims}) == 50
    assert all(document["claim_id"] in claim_ids for document in documents)
    listed = {doc_id for claim in claims for doc_id in claim["document_ids"]}
    assert listed == {document["_id"] for document in documents}


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("mongodb://localhost:27017", True),
        ("mongodb://127.0.0.1:27017,localhost:27018/intelliclaim", True),
        ("mongodb://mongodb:27017", True),
        ("mongodb://[::1]:27017", True),
        ("mongodb://user:pass@localhost:27017/db?authSource=admin", True),
        ("mongodb+srv://user:pass@cluster0.example.mongodb.net/intelliclaim", False),
        ("mongodb://db.example.com:27017", False),
        ("mongodb://localhost:27017,db.example.com:27017", False),
        ("not-a-uri", False),
    ],
)
def test_is_local_database(uri, expected):
    assert is_local_database(uri) is expected
