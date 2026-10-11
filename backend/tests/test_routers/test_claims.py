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


# --- Search input is matched literally ---------------------------------------


@pytest.mark.parametrize(
    ("term", "expected_total"),
    # Both seeded diagnoses contain a literal "(" such as "(E11.9)".
    [("(", 2), ("(E11.9)", 1), ("[a-", 0), ("*", 0), ("\\", 0)],
)
async def test_search_with_regex_metacharacters_matches_literally(async_client, term, expected_total):
    response = await async_client.get("/api/claims", params={"search": term})
    assert response.status_code == 200
    assert response.json()["total"] == expected_total


async def test_search_wildcard_is_not_interpreted(async_client):
    """'.*' used to match every claim because it was passed to $regex unescaped."""
    response = await async_client.get("/api/claims", params={"search": ".*"})
    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_search_is_case_insensitive_substring(async_client):
    response = await async_client.get("/api/claims", params={"search": "diabetes"})
    assert [c["id"] for c in response.json()["claims"]] == ["claim-test-001"]


async def test_search_length_is_capped(async_client):
    response = await async_client.get("/api/claims", params={"search": "x" * 101})
    assert response.status_code == 422


# --- PUT uses the ClaimUpdate model --------------------------------------------


async def test_update_claim_ignores_unknown_and_protected_fields(async_client, test_db):
    response = await async_client.put(
        "/api/claims/claim-test-001",
        json={"_id": "hijacked", "id": "hijacked", "document_ids": ["doc-x"], "evil": 1, "status": "pending"},
    )
    assert response.status_code == 200
    stored = await test_db.claims.find_one({"_id": "claim-test-001"})
    assert stored["status"] == "pending"
    assert stored["document_ids"] == ["doc-test-002"]
    assert "evil" not in stored
    assert await test_db.claims.find_one({"_id": "hijacked"}) is None


@pytest.mark.parametrize(
    "body",
    [
        {"status": "totally-approved"},
        {"treatment_cost": -5},
        {"treatment_cost": "a lot"},
        {"risk_score": 150},
        {"extraction_confidence": 1.5},
        {"date_of_service": "15/01/2024"},
        {"patient_name": ""},
    ],
)
async def test_update_claim_rejects_invalid_values(async_client, body):
    response = await async_client.put("/api/claims/claim-test-001", json=body)
    assert response.status_code == 422


async def test_update_claim_normalises_dates(async_client):
    response = await async_client.put("/api/claims/claim-test-001", json={"date_of_service": " 2024-02-03 "})
    assert response.status_code == 200
    assert response.json()["date_of_service"] == "2024-02-03"


async def test_update_claim_with_no_fields_is_rejected(async_client):
    response = await async_client.put("/api/claims/claim-test-001", json={"unknown": "value"})
    assert response.status_code == 400
    assert response.json() == {"detail": "No updatable fields were provided"}


async def test_update_claim_not_found(async_client):
    response = await async_client.put("/api/claims/nonexistent", json={"status": "approved"})
    assert response.status_code == 404


async def test_update_claim_duplicate_claim_number_is_a_bad_request(async_client):
    response = await async_client.put("/api/claims/claim-test-001", json={"claim_number": "CLM-002"})
    assert response.status_code == 400
    assert "already used" in response.json()["detail"]
