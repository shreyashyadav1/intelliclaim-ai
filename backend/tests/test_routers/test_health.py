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
