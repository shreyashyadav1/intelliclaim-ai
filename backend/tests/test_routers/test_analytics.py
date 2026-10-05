"""
IntelliClaim AI — Analytics Router Tests

Tests the analytics dashboard data endpoints.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pymongo.errors import ServerSelectionTimeoutError

import services.analytics_service as analytics_module


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


# --- Computed from real data only --------------------------------------------------


async def test_overview_values_come_from_the_database(async_client, test_db):
    await test_db.documents.insert_one({"_id": "doc-failed", "processing_status": "failed"})
    data = (await async_client.get("/api/analytics/overview")).json()

    assert data["claims_by_status"] == {"approved": 1, "flagged": 1}
    assert data["avg_treatment_cost"] == 53900.0
    assert data["avg_risk_score"] == 35.0
    assert data["high_risk_count"] == 1
    assert data["approval_rate"] == 50.0
    assert data["documents_processed"] == 2
    assert data["documents_failed"] == 1
    assert data["documents_total"] == 3


async def test_overview_with_no_numeric_costs_does_not_crash(async_client, test_db):
    """$avg returns null when no value is numeric; round(None) used to raise."""
    await test_db.claims.update_many({}, {"$set": {"treatment_cost": None, "risk_score": None}})
    data = (await async_client.get("/api/analytics/overview")).json()
    assert data["avg_treatment_cost"] == 0
    assert data["avg_risk_score"] == 0


async def test_overview_of_an_empty_database_is_zeroes(async_client, test_db):
    await test_db.claims.delete_many({})
    await test_db.documents.delete_many({})
    data = (await async_client.get("/api/analytics/overview")).json()
    assert data["total_claims"] == 0
    assert data["claims_by_status"] == {}
    assert data["approval_rate"] == 0


async def test_claims_trend_ends_today(async_client, test_db):
    """The window used to stop at yesterday, so claims created today never showed."""
    now = datetime.now(UTC)
    await test_db.claims.insert_many([
        {"_id": "c-today", "claim_number": "T-1", "created_at": now},
        {"_id": "c-oldest", "claim_number": "T-2", "created_at": now - timedelta(days=6)},
        {"_id": "c-outside", "claim_number": "T-3", "created_at": now - timedelta(days=7, hours=1)},
    ])

    trend = (await async_client.get("/api/analytics/claims-trend", params={"days": 7})).json()

    assert len(trend) == 7
    assert trend[-1] == {"date": now.date().isoformat(), "count": 1}
    assert trend[0] == {"date": (now.date() - timedelta(days=6)).isoformat(), "count": 1}
    assert sum(day["count"] for day in trend) == 2


async def test_recent_claims_are_real(async_client, test_db):
    assert [c["id"] for c in (await async_client.get("/api/analytics/recent-claims")).json()] == [
        "claim-test-001",
        "claim-test-002",
    ]
    await test_db.claims.delete_many({})
    assert (await async_client.get("/api/analytics/recent-claims")).json() == []


@pytest.mark.parametrize(
    "path", ["/api/analytics/overview", "/api/analytics/claims-trend", "/api/analytics/recent-claims"]
)
async def test_database_outage_is_503_not_invented_numbers(async_client, monkeypatch, path):
    def _unavailable():
        raise ServerSelectionTimeoutError("no servers")

    monkeypatch.setattr(analytics_module, "get_database", _unavailable)
    response = await async_client.get(path)
    assert response.status_code == 503
    assert set(response.json()) == {"detail"}


async def test_unexpected_failure_is_500_not_invented_numbers(async_client, monkeypatch):
    async def _broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(analytics_module.analytics_service, "get_risk_distribution", _broken)
    response = await async_client.get("/api/analytics/risk-distribution")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
