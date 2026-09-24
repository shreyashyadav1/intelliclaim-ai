"""
IntelliClaim AI — Health Router Tests

Tests the /api/health endpoint for liveness and configuration reporting.
"""

import pytest


@pytest.mark.asyncio
async def test_health_check(async_client):
    """Health endpoint returns expected structure and status."""
    response = await async_client.get("/api/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "IntelliClaim AI API"
    assert data["version"] == "1.0.0"
    assert "openai_configured" in data


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
