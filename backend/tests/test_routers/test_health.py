"""
IntelliClaim AI — Health Router Tests

/api/health reports database reachability, AI configuration and mock mode.
"""

import asyncio
import time

import pytest

import db.connection as db_conn
import main
from config import settings


async def test_health_check(async_client):
    """Health endpoint returns expected structure and status."""
    response = await async_client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "IntelliClaim AI API"
    assert data["version"] == "1.0.0"
    assert data["database"] == "ok"
    assert data["llm_configured"] is False
    assert data["mock_llm"] is False
    assert data["ai_provider"] == "none"
    assert data["openai_configured"] is False
    assert data["groq_configured"] is False


async def test_health_reports_configured_provider_without_secrets(async_client, monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_super_secret_value")
    monkeypatch.setattr(settings, "MONGODB_URI", "mongodb+srv://user:db-password@cluster0.example.net/x")

    response = await async_client.get("/api/health")

    data = response.json()
    assert data["llm_configured"] is True
    assert data["groq_configured"] is True
    assert data["ai_provider"] == "groq"
    assert "gsk_super_secret_value" not in response.text
    assert "db-password" not in response.text


async def test_health_reports_mock_mode(async_client, mock_llm):
    data = (await async_client.get("/api/health")).json()
    assert data["mock_llm"] is True
    assert data["ai_provider"] == "mock"


class _HangingDatabase:
    async def command(self, name):
        await asyncio.sleep(30)


class _BrokenDatabase:
    async def command(self, name):
        raise ConnectionError("connection refused")


@pytest.mark.parametrize("database", [_HangingDatabase(), _BrokenDatabase(), None])
async def test_unreachable_database_is_503_and_fast(async_client, monkeypatch, database):
    monkeypatch.setattr(db_conn, "_database", database)
    monkeypatch.setattr(main, "HEALTH_DB_TIMEOUT_SECONDS", 0.2)

    started = time.perf_counter()
    response = await async_client.get("/api/health")

    assert time.perf_counter() - started < 2
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["database"] == "unreachable"
    assert data["detail"] == "The database is unreachable."


# --- /api/health/groq ------------------------------------------------------------


async def test_groq_health_without_key_is_503(async_client):
    response = await async_client.get("/api/health/groq")
    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


async def test_groq_health_ok_uses_shared_async_client(async_client, fake_groq):
    fake_groq.respond('{"ok": true}')
    response = await async_client.get("/api/health/groq")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["response"] == '{"ok": true}'
    assert fake_groq.calls[0]["response_format"] == {"type": "json_object"}


async def test_groq_health_failure_is_502_without_exception_text(async_client, fake_groq, groq_errors):
    fake_groq.respond(groq_errors.connection())
    response = await async_client.get("/api/health/groq")
    assert response.status_code == 502
    body = response.json()
    assert set(body) == {"detail"}
    assert "Connection error" not in body["detail"]
    assert "APIConnectionError" not in body["detail"]


async def test_groq_health_in_mock_mode_does_not_call_groq(async_client, fake_groq, mock_llm):
    response = await async_client.get("/api/health/groq")
    assert response.status_code == 200
    assert response.json()["source"] == "mock"
    assert fake_groq.calls == []
