"""
IntelliClaim AI — Analytics Router Tests

Tests the analytics dashboard data endpoints.
"""

import pytest


@pytest.mark.asyncio
async def test_analytics_overview(async_client):
    """GET /api/analytics/overview returns aggregate stats."""
    response = await async_client.get("/api/analytics/overview")
    assert response.status_code == 200

    data = response.json()
    assert data["total_claims"] == 2
    assert data["documents_processed"] == 2
    assert "claims_by_status" in data
    assert "avg_treatment_cost" in data
    assert "avg_risk_score" in data
    assert "high_risk_count" in data
    assert "approval_rate" in data


@pytest.mark.asyncio
async def test_analytics_risk_distribution(async_client):
    """Risk distribution endpoint returns buckets."""
    response = await async_client.get("/api/analytics/risk-distribution")
    assert response.status_code == 200

    data = response.json()
    # Response is a list of buckets, not wrapped in a dict
    assert isinstance(data, list)
    assert len(data) >= 2
    labels = [bucket["range"] for bucket in data]
    assert any("Low" in label for label in labels)
