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
    assert data["ai_review"]["ai_summary"] == "AI review not available (no API key configured)."


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


# --- Provider failures and batch limits ----------------------------------------------------

GOOD_REVIEW = {"risk_flags": [], "ai_risk_score": 10, "summary": "Looks consistent."}


async def test_validate_provider_failure_is_502_and_leaves_claim_unchanged(
    async_client, test_db, fake_groq, groq_errors
):
    before = await test_db.claims.find_one({"_id": "claim-test-002"})
    fake_groq.respond(groq_errors.connection())

    response = await async_client.post("/api/validate/claim-test-002")

    assert response.status_code == 502
    assert set(response.json()) == {"detail"}
    after = await test_db.claims.find_one({"_id": "claim-test-002"})
    assert after["risk_score"] == before["risk_score"]
    assert after["updated_at"] == before["updated_at"]


async def test_validate_with_ai_review_stores_the_composite_score(async_client, test_db, fake_groq):
    fake_groq.respond(GOOD_REVIEW)
    response = await async_client.post("/api/validate/claim-test-001")

    assert response.status_code == 200
    assert response.json()["ai_review"]["status"] == "completed"
    stored = await test_db.claims.find_one({"_id": "claim-test-001"})
    assert stored["risk_score"] == response.json()["risk_score"]


async def test_batch_validate_rejects_more_than_100_ids(async_client):
    response = await async_client.post("/api/batch-validate", json={"claim_ids": [f"c{i}" for i in range(101)]})
    assert response.status_code == 422


async def test_batch_validate_accepts_exactly_100_ids(async_client):
    response = await async_client.post("/api/batch-validate", json={"claim_ids": [f"c{i}" for i in range(100)]})
    assert response.status_code == 200
    assert response.json()["total_requested"] == 100


@pytest.mark.parametrize("body", [{"claim_ids": []}, {"claim_ids": [""]}, {"claim_ids": ["x" * 101]}, {}])
async def test_batch_validate_rejects_invalid_payloads(async_client, body):
    response = await async_client.post("/api/batch-validate", json=body)
    assert response.status_code == 422


async def test_batch_validate_counts_only_successful_validations(async_client):
    response = await async_client.post(
        "/api/batch-validate", json={"claim_ids": ["claim-test-001", "missing", "claim-test-001"]}
    )
    data = response.json()
    assert data["total_requested"] == 2  # duplicates are validated once
    assert data["total_validated"] == 1
    assert data["errors"] == 1
    assert data["results"][1] == {"claim_id": "missing", "error": "Not found"}


async def test_batch_validate_stops_calling_a_failing_provider(async_client, fake_groq, groq_errors):
    fake_groq.respond(GOOD_REVIEW, groq_errors.connection())
    response = await async_client.post(
        "/api/batch-validate", json={"claim_ids": ["claim-test-001", "claim-test-002", "missing"]}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_validated"] == 1
    assert "risk_score" in data["results"][0]
    assert "error" in data["results"][1]
    assert data["results"][2]["error"].startswith("Skipped")
    assert len(fake_groq.calls) == 2


async def test_batch_validate_is_502_when_nothing_could_be_validated(async_client, fake_groq, groq_errors):
    fake_groq.respond(groq_errors.connection())
    response = await async_client.post("/api/batch-validate", json={"claim_ids": ["claim-test-001", "claim-test-002"]})
    assert response.status_code == 502
