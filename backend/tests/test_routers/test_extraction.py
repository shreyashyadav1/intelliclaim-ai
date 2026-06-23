"""
IntelliClaim AI — Extraction Router Tests

Covers: POST /api/extract/{document_id} and GET /api/extract/{document_id}/results.
Key regression: extracted fields must be populated in the created claim (not empty {}).
"""

import pytest


@pytest.mark.asyncio
async def test_extract_creates_claim_with_fields(async_client):
    """POST /extract creates a claim with actual extracted fields, not empty data."""
    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200

    data = response.json()
    assert data["is_new_claim"] is True
    assert "claim_id" in data
    assert data["confidence_score"] > 0

    # This is the regression check: extracted_data must contain real fields
    extracted = data["extracted_data"]
    assert extracted, "extracted_data must not be empty"
    assert "patient_name" in extracted
    assert "treatment_cost" in extracted
    assert "hospital_name" in extracted


@pytest.mark.asyncio
async def test_extract_claim_stored_in_db(async_client, test_db):
    """Extracted fields must be persisted in the claim document in MongoDB."""
    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200

    claim_id = response.json()["claim_id"]
    claim = await test_db.claims.find_one({"_id": claim_id})
    assert claim is not None

    # Claim must have actual field data, not just metadata fields
    assert claim.get("patient_name"), "patient_name not stored in claim"
    assert claim.get("treatment_cost"), "treatment_cost not stored in claim"
    assert claim.get("hospital_name"), "hospital_name not stored in claim"
    assert claim.get("extraction_confidence", 0) > 0


@pytest.mark.asyncio
async def test_extract_links_document_to_claim(async_client, test_db):
    """After extraction, the document record is updated with the new claim_id."""
    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200

    claim_id = response.json()["claim_id"]
    doc = await test_db.documents.find_one({"_id": "doc-test-001"})
    assert doc["claim_id"] == claim_id


@pytest.mark.asyncio
async def test_extract_updates_existing_claim(async_client):
    """POST /extract on a document that already has a claim_id updates instead of creating."""
    response = await async_client.post("/api/extract/doc-test-002")
    assert response.status_code == 200

    data = response.json()
    assert data["is_new_claim"] is False
    assert data["claim_id"] == "claim-test-001"


@pytest.mark.asyncio
async def test_extract_document_not_found(async_client):
    """POST /extract returns 404 for an unknown document ID."""
    response = await async_client.post("/api/extract/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_extraction_results_with_claim(async_client):
    """GET /extract/{id}/results returns the linked claim for an extracted document."""
    response = await async_client.get("/api/extract/doc-test-002/results")
    assert response.status_code == 200

    data = response.json()
    assert data["extracted"] is True
    assert data["claim"] is not None
    assert data["claim"]["id"] == "claim-test-001"


@pytest.mark.asyncio
async def test_get_extraction_results_not_extracted(async_client):
    """GET /extract/{id}/results returns extracted=False when no claim exists yet."""
    response = await async_client.get("/api/extract/doc-test-001/results")
    assert response.status_code == 200

    data = response.json()
    assert data["extracted"] is False
    assert data["claim"] is None
