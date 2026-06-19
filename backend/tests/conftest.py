"""
IntelliClaim AI — Test Configuration & Fixtures

Provides:
- async_client: httpx.AsyncClient for async API testing with a test DB
- seed_test_db: fixture that seeds known test data before each test
"""

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import sys, os
sys.path.insert(0, os.path.dirname(__file__) + "/..")

from main import app
from motor.motor_asyncio import AsyncIOMotorClient

TEST_DB_NAME = "intelliclaim_test"
TEST_MONGO_URI = "mongodb://localhost:27017"


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """Create a fresh Motor client per test to avoid event-loop binding issues."""
    client = AsyncIOMotorClient(TEST_MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[TEST_DB_NAME]

    # Verify connectivity
    await client.admin.command("ping")

    # Clear collections
    await db.claims.delete_many({})
    await db.documents.delete_many({})

    # Seed test documents
    await db.documents.insert_many([
        {
            "_id": "doc-test-001",
            "filename": "invoice_test.pdf",
            "file_type": "pdf",
            "file_size": 1024,
            "storage_path": "./uploads/documents/doc-test-001.pdf",
            "document_class": "invoice",
            "extracted_text": "Patient: John Doe. Policy: POL-001. Diagnosis: Appendicitis. Treatment Cost: $28,500. Date: 2024-01-15.",
            "claim_id": None,
            "processing_status": "processed",
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
        },
        {
            "_id": "doc-test-002",
            "filename": "claim_form_test.pdf",
            "file_type": "pdf",
            "file_size": 2048,
            "storage_path": "./uploads/documents/doc-test-002.pdf",
            "document_class": "claim_form",
            "extracted_text": "Claim Number: CLM-001. Patient: Jane Smith. Policy: POL-002. Diagnosis: Type 2 Diabetes. Hospital: Metro General.",
            "claim_id": "claim-test-001",
            "processing_status": "processed",
            "created_at": "2024-01-16T11:00:00Z",
            "updated_at": "2024-01-16T11:00:00Z",
        },
    ])

    # Seed test claims
    await db.claims.insert_many([
        {
            "_id": "claim-test-001",
            "claim_number": "CLM-001",
            "policy_number": "POL-002",
            "patient_name": "Jane Smith",
            "diagnosis": "Type 2 Diabetes Mellitus (E11.9)",
            "treatment_cost": 12800.00,
            "hospital_name": "Metro General Hospital",
            "hospital_address": "450 Medical Center Dr, New York, NY 10016",
            "provider_id": "NPI-1234567890",
            "date_of_service": "2024-01-16",
            "date_of_admission": "2024-01-16",
            "date_of_discharge": "2024-01-20",
            "status": "approved",
            "risk_score": 5.0,
            "risk_flags": [],
            "document_ids": ["doc-test-002"],
            "extraction_confidence": 0.91,
            "created_at": "2024-01-16T11:00:00Z",
            "updated_at": "2024-01-16T11:00:00Z",
        },
        {
            "_id": "claim-test-002",
            "claim_number": "CLM-002",
            "policy_number": "POL-003",
            "patient_name": "John Doe",
            "diagnosis": "Acute Appendicitis (K35.80)",
            "treatment_cost": 95000.00,
            "hospital_name": "Cedar Ridge Medical Center",
            "hospital_address": "1200 Health Pkwy, Chicago, IL 60601",
            "provider_id": "NPI-0987654321",
            "date_of_service": "2024-01-15",
            "date_of_admission": "2024-01-15",
            "date_of_discharge": "2024-01-18",
            "status": "flagged",
            "risk_score": 65.0,
            "risk_flags": ["Treatment cost exceeds $50,000 threshold"],
            "document_ids": ["doc-test-001"],
            "extraction_confidence": 0.85,
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
        },
    ])

    yield db

    # Cleanup
    await client.drop_database(TEST_DB_NAME)
    client.close()


@pytest_asyncio.fixture
async def async_client(test_db) -> AsyncGenerator[AsyncClient, None]:
    """Provide an httpx AsyncClient with DB overridden to the test database."""
    # Monkeypatch the module-level _database variable
    import db.connection as db_conn
    original_db = db_conn._database
    db_conn._database = test_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    db_conn._database = original_db
