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

import hashlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
from collections.abc import AsyncGenerator  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import groq  # noqa: E402
import httpx  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from chromadb.api.shared_system_client import SharedSystemClient  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from config import settings  # noqa: E402
from main import app  # noqa: E402
from services import llm  # noqa: E402

TEST_MONGO_URI = os.environ.get("TEST_MONGODB_URI", "mongodb://localhost:27017")
TEST_DB_NAME = f"intelliclaim_test_{os.getpid()}"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


# --- AI provider fakes ----------------------------------------------------------


class FakeGroq:
    """Stands in for groq.AsyncGroq. Queue replies with respond(); inspect calls."""

    def __init__(self) -> None:
        self._replies: list = []
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def respond(self, *replies) -> "FakeGroq":
        """Queue replies: dicts are sent as JSON text, exceptions are raised."""
        for reply in replies:
            self._replies.append(json.dumps(reply) if isinstance(reply, dict) else reply)
        return self

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._replies:
            raise AssertionError("FakeGroq received a request with no reply queued")
        reply = self._replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])

    async def close(self) -> None:
        pass


def groq_connection_error() -> groq.APIConnectionError:
    return groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))


def groq_rate_limit_error() -> groq.RateLimitError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return groq.RateLimitError("rate limited", response=httpx.Response(429, request=request), body=None)


@pytest.fixture(autouse=True)
def ai_client_guard(monkeypatch) -> SimpleNamespace:
    """Fail loudly if any code path tries to build a real provider client.

    Returns the original factories for the tests that check how they are built.
    """
    originals = SimpleNamespace(groq=llm._create_groq_client, openai=llm._create_openai_client)

    def _forbidden():
        raise AssertionError("Tests must not create real AI provider clients; use the fake_groq fixture")

    monkeypatch.setattr(llm, "_create_groq_client", _forbidden)
    monkeypatch.setattr(llm, "_create_openai_client", _forbidden)
    monkeypatch.setattr(llm, "_groq_client", None)
    monkeypatch.setattr(llm, "_openai_client", None)
    return originals


@pytest.fixture
def fake_groq(monkeypatch) -> FakeGroq:
    """Configure a Groq key and route all Groq calls to a FakeGroq instance."""
    fake = FakeGroq()
    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-groq-key")
    monkeypatch.setattr(llm, "_groq_client", fake)
    return fake


@pytest.fixture
def groq_errors() -> SimpleNamespace:
    """Factories for the exceptions the Groq SDK raises."""
    return SimpleNamespace(connection=groq_connection_error, rate_limit=groq_rate_limit_error)


@pytest.fixture
def mock_llm(monkeypatch) -> None:
    monkeypatch.setattr(settings, "MOCK_LLM", True)


# --- File storage -------------------------------------------------------------------


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    """Store uploads in a per-test directory (an absolute path, like a mounted volume)."""
    from services.storage_service import storage_service

    base = tmp_path / "uploads"
    monkeypatch.setattr(storage_service, "base_path", base)
    return base


# --- Vector store -------------------------------------------------------------------


class FakeEmbedder:
    """Deterministic bag-of-words vectors, so tests never load or download fastembed."""

    DIM = 64

    def embed(self, texts):
        for text in texts:
            vector = np.zeros(self.DIM)
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM] += 1.0
            norm = np.linalg.norm(vector)
            if norm:
                vector /= norm
            else:
                vector[0] = 1.0
            yield vector


@pytest.fixture(autouse=True)
def isolated_vector_store(tmp_path, monkeypatch) -> SimpleNamespace:
    """Give each test its own ChromaDB directory and the fake embedder.

    Returns the original _get_embedder for the tests that check how it loads fastembed.
    """
    import services.rag_service as rag_module

    originals = SimpleNamespace(get_embedder=rag_module._get_embedder)
    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    monkeypatch.setattr(rag_module, "_chroma_client", None)
    monkeypatch.setattr(rag_module, "_chroma_collection", None)
    monkeypatch.setattr(rag_module, "_embedder", None)
    monkeypatch.setattr(rag_module, "_get_embedder", FakeEmbedder)
    yield originals
    SharedSystemClient.clear_system_cache()


# --- Database -----------------------------------------------------------------------


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
