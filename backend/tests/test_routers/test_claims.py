"""
IntelliClaim AI — Claims Router Tests

Tests CRUD operations, filtering, and pagination on the claims API.
"""

import pytest


@pytest.mark.asyncio
async def test_list_claims(async_client):
    """GET /api/claims returns the seeded claims with pagination."""
    response = await async_client.get("/api/claims")
    assert response.status_code == 200

    data = response.json()
    assert "claims" in data
    assert "total" in data
    assert data["total"] == 2
    assert len(data["claims"]) == 2


@pytest.mark.asyncio
async def test_list_claims_with_status_filter(async_client):
    """Status filter narrows the result set."""
    response = await async_client.get("/api/claims?status=approved")
    assert response.status_code == 200

    data = response.json()
    assert all(c["status"] == "approved" for c in data["claims"])


@pytest.mark.asyncio
async def test_list_claims_with_risk_level_filter(async_client):
    """Risk level filter buckets claims correctly."""
    response = await async_client.get("/api/claims?risk_level=high")
    assert response.status_code == 200

    data = response.json()
    for claim in data["claims"]:
        assert claim["risk_score"] >= 60


@pytest.mark.asyncio
async def test_list_claims_search(async_client):
    """Search string matches patient name, diagnosis, or claim number."""
    response = await async_client.get("/api/claims?search=Jane")
    assert response.status_code == 200

    data = response.json()
    assert len(data["claims"]) >= 1
    assert any("Jane" in str(claim.get("patient_name", "")) for claim in data["claims"])


@pytest.mark.asyncio
async def test_get_claim_by_id(async_client):
    """GET /api/claims/{id} returns the correct claim."""
    response = await async_client.get("/api/claims/claim-test-001")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == "claim-test-001"
    assert data["claim_number"] == "CLM-001"
    assert data["patient_name"] == "Jane Smith"


@pytest.mark.asyncio
async def test_get_claim_not_found(async_client):
    """GET /api/claims/{id} returns 404 for unknown ID."""
    response = await async_client.get("/api/claims/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_claim(async_client):
    """PUT /api/claims/{id} updates claim fields."""
    response = await async_client.put(
        "/api/claims/claim-test-001",
        json={"status": "rejected", "treatment_cost": 9999.00},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "rejected"
    assert data["treatment_cost"] == 9999.00


@pytest.mark.asyncio
async def test_delete_claim(async_client):
    """DELETE /api/claims/{id} removes the claim."""
    response = await async_client.delete("/api/claims/claim-test-001")
    assert response.status_code == 200

    # Verify it's gone
    response = await async_client.get("/api/claims/claim-test-001")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_claim_documents(async_client):
    """GET /api/claims/{id}/documents returns associated documents."""
    response = await async_client.get("/api/claims/claim-test-001/documents")
    assert response.status_code == 200

    data = response.json()
    assert "documents" in data
    assert len(data["documents"]) >= 1
