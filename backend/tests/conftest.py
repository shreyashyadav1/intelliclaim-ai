"""
IntelliClaim AI - shared test fixtures.

- test_db: a fresh MongoDB database seeded with known documents and claims.
- async_client: an httpx.AsyncClient wired to the FastAPI app and test_db.

MongoDB is taken from TEST_MONGODB_URI (default mongodb://localhost:27017).
"""

import os

# Environment variables take precedence over backend/.env, so blanking the
# provider keys here guarantees the suite never reaches a real AI provider,
# whatever a developer keeps in their local .env file.
os.environ.update(
    {
        "GROQ_API_KEY": "",
        "OPENAI_API_KEY": "",
        "MOCK_LLM": "false",
        "ADMIN_API_KEY": "",
    }
)

from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from main import app  # noqa: E402

TEST_MONGO_URI = os.environ.get("TEST_MONGODB_URI", "mongodb://localhost:27017")
TEST_DB_NAME = f"intelliclaim_test_{os.getpid()}"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


@pytest_asyncio.fixture
async def test_db():
    """Create a fresh Motor client per test to avoid event-loop binding issues."""
    client = AsyncIOMotorClient(TEST_MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[TEST_DB_NAME]
    await client.admin.command("ping")

    await db.claims.delete_many({})
    await db.documents.delete_many({})
    await db.claims.create_index("claim_number", unique=True)

    await db.documents.insert_many([
        {
            "_id": "doc-test-001",
            "filename": "invoice_test.pdf",
            "file_type": "pdf",
            "file_size": 1024,
            "storage_path": "./uploads/documents/doc-test-001.pdf",
            "document_class": "invoice",
            "extracted_text": (
                "Patient: John Doe. Policy: POL-001. Diagnosis: Appendicitis. "
                "Treatment Cost: $28,500. Date: 2024-01-15."
            ),
            "claim_id": None,
            "processing_status": "processed",
            "created_at": _dt("2024-01-15T10:00:00"),
            "updated_at": _dt("2024-01-15T10:00:00"),
        },
        {
            "_id": "doc-test-002",
            "filename": "claim_form_test.pdf",
            "file_type": "pdf",
            "file_size": 2048,
            "storage_path": "./uploads/documents/doc-test-002.pdf",
            "document_class": "claim_form",
            "extracted_text": (
                "Claim Number: CLM-001. Patient: Jane Smith. Policy: POL-002. "
                "Diagnosis: Type 2 Diabetes. Hospital: Metro General."
            ),
            "claim_id": "claim-test-001",
            "processing_status": "processed",
            "created_at": _dt("2024-01-16T11:00:00"),
            "updated_at": _dt("2024-01-16T11:00:00"),
        },
    ])

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
            "created_at": _dt("2024-01-16T11:00:00"),
            "updated_at": _dt("2024-01-16T11:00:00"),
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
            "document_ids": [],
            "extraction_confidence": 0.85,
            "created_at": _dt("2024-01-15T10:00:00"),
            "updated_at": _dt("2024-01-15T10:00:00"),
        },
    ])

    yield db

    await client.drop_database(TEST_DB_NAME)
    client.close()


@pytest_asyncio.fixture
async def async_client(test_db) -> AsyncGenerator[AsyncClient]:
    """Provide an httpx AsyncClient with the app's database pointed at test_db."""
    import db.connection as db_conn

    original_db = db_conn._database
    db_conn._database = test_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    db_conn._database = original_db
