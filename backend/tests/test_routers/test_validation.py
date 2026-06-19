"""
IntelliClaim AI — Validation Router Tests

Tests risk validation endpoints, batch validation, and flagged claims listing.
"""

import pytest


@pytest.mark.asyncio
async def test_validate_single_claim(async_client):
    """POST /api/validate/{claim_id} runs validation and returns risk assessment."""
    response = await async_client.post("/api/validate/claim-test-002")
    assert response.status_code == 200

    data = response.json()
    assert data["claim_id"] == "claim-test-002"
    assert "risk_score" in data
    assert "risk_level" in data
    assert "flags" in data
    assert "is_duplicate" in data
    assert "ai_review" in data
    assert data["ai_review"]["ai_summary"] == "AI review not available (no OpenAI key configured)."


@pytest.mark.asyncio
async def test_validate_claim_not_found(async_client):
    """POST /api/validate/{id} returns 404 for unknown claim."""
    response = await async_client.post("/api/validate/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_batch_validate(async_client):
    """POST /api/batch-validate validates multiple claims."""
    response = await async_client.post(
        "/api/batch-validate",
        json={"claim_ids": ["claim-test-001", "claim-test-002"]},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["total_validated"] == 2
    results = data["results"]
    assert len(results) == 2

    # Verify each result has the expected structure
    for result in results:
        assert "claim_id" in result
        assert "risk_score" in result
        assert "risk_level" in result
        assert "flags" in result
        assert "ai_review" in result


@pytest.mark.asyncio
async def test_get_flagged_claims(async_client):
    """GET /api/validate/flagged returns high-risk claims."""
    response = await async_client.get("/api/validate/flagged")
    assert response.status_code == 200

    data = response.json()
    assert "claims" in data
    assert "total" in data
    # At least one claim is flagged in our seed data
    assert data["total"] >= 1
    for claim in data["claims"]:
        assert claim["status"] == "flagged" or claim["risk_score"] >= 30
