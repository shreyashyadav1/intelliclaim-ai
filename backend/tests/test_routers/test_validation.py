"""
IntelliClaim AI — Validation Router Tests

Tests risk validation endpoints, batch validation, and flagged claims listing.
"""

import pytest

from config import settings


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
    assert data["flag_threshold"] == settings.RISK_FLAG_THRESHOLD
    for claim in data["claims"]:
        assert claim["status"] == "flagged" or claim["risk_score"] >= settings.RISK_FLAG_THRESHOLD


async def test_flagged_list_includes_medium_risk_claims_from_the_threshold(async_client, test_db, monkeypatch):
    monkeypatch.setattr(settings, "RISK_FLAG_THRESHOLD", 15.0)
    await test_db.claims.insert_many([
        {"_id": "claim-medium", "claim_number": "CLM-MED", "status": "pending", "risk_score": 15.0},
        {"_id": "claim-low", "claim_number": "CLM-LOW", "status": "pending", "risk_score": 14.9},
    ])

    data = (await async_client.get("/api/validate/flagged")).json()
    listed = [claim["id"] for claim in data["claims"]]
    # claim-test-002 is flagged (65), claim-test-001 is approved at 5: highest score first
    assert listed == ["claim-test-002", "claim-medium"]
    assert data["total"] == 2

    monkeypatch.setattr(settings, "RISK_FLAG_THRESHOLD", 30.0)
    data = (await async_client.get("/api/validate/flagged")).json()
    assert [claim["id"] for claim in data["claims"]] == ["claim-test-002"]
    assert data["flag_threshold"] == 30.0


async def test_validation_flags_status_only_at_high_risk(async_client, test_db):
    await test_db.claims.insert_one({
        "_id": "claim-costly", "claim_number": "CLM-COSTLY", "policy_number": "POL-9", "patient_name": "Ana Ruiz",
        "diagnosis": "Hip fracture", "treatment_cost": 70000, "hospital_name": "Mercy", "status": "pending",
    })
    data = (await async_client.post("/api/validate/claim-costly")).json()
    assert (data["risk_score"], data["risk_level"]) == (15.0, "medium")  # high_cost only

    stored = await test_db.claims.find_one({"_id": "claim-costly"})
    assert stored["status"] == "pending"  # listed as flagged by score, status unchanged
    listed = (await async_client.get("/api/validate/flagged")).json()["claims"]
    assert "claim-costly" in [claim["id"] for claim in listed]


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
