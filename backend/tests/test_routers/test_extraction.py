"""
IntelliClaim AI - Extraction Router Tests

Covers POST /api/extract/{document_id} and GET /api/extract/{document_id}/results.
Provider calls go to the FakeGroq fixture; nothing reaches a real AI provider.
"""

import logging

import pytest

from config import settings
from services import llm

FULL_EXTRACTION = {
    "policy_number": "POL-001",
    "claim_number": "CLM-9001",
    "patient_name": "John Doe",
    "diagnosis": "Acute Appendicitis (K35.80)",
    "treatment_cost": 28500,
    "hospital_name": "Metro General Hospital",
    "hospital_address": "450 Medical Center Dr, New York, NY",
    "provider_id": "NPI-1234567890",
    "date_of_service": "2024-01-15",
    "date_of_admission": "2024-01-15",
    "date_of_discharge": "2024-01-18",
}


async def _claim_count(test_db) -> int:
    return await test_db.claims.count_documents({})


# --- Real extraction path (fake Groq) ---------------------------------------------


async def test_extract_creates_claim_with_fields(async_client, fake_groq):
    fake_groq.respond(FULL_EXTRACTION)
    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200

    data = response.json()
    assert data["is_new_claim"] is True
    assert data["source"] == "groq"
    assert data["claim_number"] == "CLM-9001"
    assert data["confidence_score"] == 1.0
    assert data["completeness"] == 1.0
    assert data["input_truncated"] is False
    assert data["extracted_data"] == {**FULL_EXTRACTION, "treatment_cost": 28500.0}


async def test_extract_claim_stored_in_db(async_client, test_db, fake_groq):
    fake_groq.respond(FULL_EXTRACTION)
    claim_id = (await async_client.post("/api/extract/doc-test-001")).json()["claim_id"]

    claim = await test_db.claims.find_one({"_id": claim_id})
    assert claim["patient_name"] == "John Doe"
    assert claim["treatment_cost"] == 28500.0
    assert claim["hospital_name"] == "Metro General Hospital"
    assert claim["status"] == "pending"
    assert claim["document_ids"] == ["doc-test-001"]
    assert claim["extraction_confidence"] == 1.0
    assert claim["extraction_source"] == "groq"
    assert claim["claim_number_is_placeholder"] is False


async def test_extract_links_document_to_claim(async_client, test_db, fake_groq):
    fake_groq.respond(FULL_EXTRACTION)
    claim_id = (await async_client.post("/api/extract/doc-test-001")).json()["claim_id"]
    doc = await test_db.documents.find_one({"_id": "doc-test-001"})
    assert doc["claim_id"] == claim_id


async def test_extract_updates_existing_claim(async_client, test_db, fake_groq):
    """A document already linked to a claim updates that claim in place."""
    fake_groq.respond({"claim_number": "CLM-001", "patient_name": "Jane A. Smith", "treatment_cost": "13,100"})
    response = await async_client.post("/api/extract/doc-test-002")
    assert response.status_code == 200

    data = response.json()
    assert data["is_new_claim"] is False
    assert data["claim_id"] == "claim-test-001"
    claim = await test_db.claims.find_one({"_id": "claim-test-001"})
    assert claim["patient_name"] == "Jane A. Smith"
    assert claim["treatment_cost"] == 13100.0
    assert claim["hospital_name"] == "Metro General Hospital"  # untouched: not in this extraction
    assert await _claim_count(test_db) == 2


async def test_prompt_separates_instructions_from_document_text(async_client, fake_groq):
    fake_groq.respond(FULL_EXTRACTION)
    await async_client.post("/api/extract/doc-test-001")

    call = fake_groq.calls[0]
    assert call["model"] == settings.GROQ_MODEL
    assert call["response_format"] == {"type": "json_object"}
    system, user = call["messages"]
    assert system["role"] == "system" and "JSON" in system["content"]
    assert "Patient: John Doe" in user["content"]


# --- Output validation -----------------------------------------------------------------


async def test_model_output_cannot_set_protected_fields(async_client, test_db, fake_groq):
    fake_groq.respond({
        **FULL_EXTRACTION,
        "_id": "attacker-chosen-id",
        "status": "approved",
        "risk_score": 0,
        "document_ids": ["doc-test-002"],
        "extraction_confidence": 1,
    })
    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200

    claim = await test_db.claims.find_one({"_id": response.json()["claim_id"]})
    assert claim["_id"] != "attacker-chosen-id"
    assert await test_db.claims.find_one({"_id": "attacker-chosen-id"}) is None
    assert claim["status"] == "pending"
    assert claim["document_ids"] == ["doc-test-001"]
    assert "_id" not in response.json()["extracted_data"]


async def test_model_output_types_are_coerced(async_client, test_db, fake_groq):
    fake_groq.respond({
        "claim_number": 55012,
        "patient_name": "  John   Doe ",
        "treatment_cost": "$28,500.50 USD",
        "hospital_name": {"name": "nested objects are rejected"},
        "diagnosis": "N/A",
        "date_of_service": "01/15/2024",
        "date_of_admission": "January 14, 2024",
        "date_of_discharge": "sometime in spring",
    })
    data = (await async_client.post("/api/extract/doc-test-001")).json()["extracted_data"]

    assert data["claim_number"] == "55012"
    assert data["patient_name"] == "John Doe"
    assert data["treatment_cost"] == 28500.5
    assert data["hospital_name"] is None
    assert data["diagnosis"] is None
    assert data["date_of_service"] == "2024-01-15"
    assert data["date_of_admission"] == "2024-01-14"
    assert data["date_of_discharge"] is None


async def test_confidence_counts_known_fields_only(async_client, fake_groq):
    """Extra keys used to push filled/11 above 1.0."""
    fake_groq.respond({**FULL_EXTRACTION, **{f"extra_{i}": "x" for i in range(9)}})
    assert (await async_client.post("/api/extract/doc-test-001")).json()["confidence_score"] == 1.0


async def test_partial_extraction_confidence(async_client, fake_groq):
    fake_groq.respond({"patient_name": "John Doe", "policy_number": "POL-001", "junk": 1, "more_junk": 2})
    assert (await async_client.post("/api/extract/doc-test-001")).json()["confidence_score"] == 0.18


async def test_wrapped_output_is_unwrapped(async_client, fake_groq):
    fake_groq.respond({"claim": FULL_EXTRACTION})
    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200
    assert response.json()["extracted_data"]["claim_number"] == "CLM-9001"


# --- Claim numbers ---------------------------------------------------------------------


async def test_missing_claim_number_gets_placeholder(async_client, test_db, fake_groq):
    fake_groq.respond({k: v for k, v in FULL_EXTRACTION.items() if k != "claim_number"})
    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200

    data = response.json()
    assert data["claim_number"].startswith("UNASSIGNED-")
    assert data["extracted_data"]["claim_number"] is None
    claim = await test_db.claims.find_one({"_id": data["claim_id"]})
    assert claim["claim_number_is_placeholder"] is True
    assert claim["extraction_confidence"] == 0.91  # the placeholder does not count as found


async def test_two_documents_without_claim_numbers_do_not_collide(async_client, test_db, fake_groq):
    """Two claims without a number used to hit the unique index (both null) and return 500."""
    await test_db.documents.insert_one({
        "_id": "doc-test-003", "extracted_text": "Patient: Ann Lee", "claim_id": None, "processing_status": "processed",
    })
    fake_groq.respond({"patient_name": "John Doe"}, {"patient_name": "Ann Lee"})

    first = await async_client.post("/api/extract/doc-test-001")
    second = await async_client.post("/api/extract/doc-test-003")

    assert first.status_code == second.status_code == 200
    assert first.json()["claim_id"] != second.json()["claim_id"]
    assert first.json()["claim_number"] != second.json()["claim_number"]


async def test_second_document_with_same_claim_number_links_existing_claim(async_client, test_db, fake_groq):
    """Used to raise DuplicateKeyError (500) because a second claim was inserted."""
    await test_db.documents.insert_one({
        "_id": "doc-test-003",
        "extracted_text": "Claim Number: CLM-002. Invoice total $96,000",
        "claim_id": None,
        "processing_status": "processed",
    })
    fake_groq.respond({"claim_number": "CLM-002", "treatment_cost": 96000, "provider_id": "NPI-NEW"})

    response = await async_client.post("/api/extract/doc-test-003")
    assert response.status_code == 200

    data = response.json()
    assert data["claim_id"] == "claim-test-002"
    assert data["is_new_claim"] is False
    claim = await test_db.claims.find_one({"_id": "claim-test-002"})
    assert "doc-test-003" in claim["document_ids"]
    # A second document only fills gaps; it does not overwrite existing values.
    assert claim["treatment_cost"] == 95000.0
    assert claim["provider_id"] == "NPI-0987654321"
    assert (await test_db.documents.find_one({"_id": "doc-test-003"}))["claim_id"] == "claim-test-002"
    assert await _claim_count(test_db) == 2


async def test_reextraction_replaces_placeholder_claim_number(async_client, test_db, fake_groq):
    fake_groq.respond({"patient_name": "John Doe"}, {"patient_name": "John Doe", "claim_number": "CLM-7777"})
    first = (await async_client.post("/api/extract/doc-test-001")).json()
    second = (await async_client.post("/api/extract/doc-test-001")).json()

    assert second["claim_id"] == first["claim_id"]
    assert second["claim_number"] == "CLM-7777"
    claim = await test_db.claims.find_one({"_id": first["claim_id"]})
    assert claim["claim_number"] == "CLM-7777"
    assert claim["claim_number_is_placeholder"] is False


async def test_reextraction_with_a_number_owned_by_another_claim_keeps_the_current_one(
    async_client, test_db, fake_groq
):
    fake_groq.respond({"claim_number": "CLM-002", "patient_name": "Jane Smith"})
    response = await async_client.post("/api/extract/doc-test-002")

    assert response.status_code == 200
    assert response.json()["claim_number"] == "CLM-001"
    assert (await test_db.claims.find_one({"_id": "claim-test-001"}))["claim_number"] == "CLM-001"


async def test_stale_claim_link_is_repaired(async_client, test_db, fake_groq):
    await test_db.documents.update_one({"_id": "doc-test-001"}, {"$set": {"claim_id": "deleted-claim"}})
    fake_groq.respond(FULL_EXTRACTION)
    response = await async_client.post("/api/extract/doc-test-001")

    assert response.status_code == 200
    assert response.json()["is_new_claim"] is True
    assert (await test_db.documents.find_one({"_id": "doc-test-001"}))["claim_id"] == response.json()["claim_id"]


# --- Failures never write fabricated data -------------------------------------------------


async def test_extract_without_provider_is_503_and_writes_nothing(async_client, test_db):
    response = await async_client.post("/api/extract/doc-test-001")

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]
    assert await _claim_count(test_db) == 2
    assert (await test_db.documents.find_one({"_id": "doc-test-001"}))["claim_id"] is None


async def test_extract_provider_failure_is_502_and_writes_nothing(async_client, test_db, fake_groq, groq_errors):
    fake_groq.respond(groq_errors.connection())
    response = await async_client.post("/api/extract/doc-test-001")

    assert response.status_code == 502
    assert response.json() == {"detail": llm.LLMProviderError.default_detail}
    assert await _claim_count(test_db) == 2


@pytest.mark.parametrize("reply", ["this is not json", "[1, 2, 3]", '{"unrelated": "keys"}'])
async def test_unusable_model_output_is_502(async_client, test_db, fake_groq, reply):
    fake_groq.respond(reply)
    response = await async_client.post("/api/extract/doc-test-001")

    assert response.status_code == 502
    assert await _claim_count(test_db) == 2


async def test_openai_failure_falls_back_to_groq(async_client, fake_groq, monkeypatch):
    async def _openai_down(*args, **kwargs):
        raise llm.LLMProviderError()

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(llm, "openai_tool_call", _openai_down)
    fake_groq.respond(FULL_EXTRACTION)

    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200
    assert response.json()["source"] == "groq"


async def test_openai_extraction_is_validated_too(async_client, test_db, monkeypatch):
    async def _openai_tool_call(messages, params, tool):
        assert tool["function"]["name"] == "extract_claim_fields"
        return {**FULL_EXTRACTION, "status": "approved"}

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setattr(llm, "openai_tool_call", _openai_tool_call)

    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200
    assert response.json()["source"] == "openai"
    claim = await test_db.claims.find_one({"_id": response.json()["claim_id"]})
    assert claim["status"] == "pending"


# --- Mock mode -------------------------------------------------------------------------------


async def test_mock_mode_is_labelled_and_reads_the_document(async_client, test_db, mock_llm, fake_groq):
    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 200

    data = response.json()
    assert data["source"] == "mock"
    assert data["extracted_data"]["patient_name"] == "John Doe"
    assert data["extracted_data"]["policy_number"] == "POL-001"
    assert data["extracted_data"]["treatment_cost"] == 28500.0
    assert data["extracted_data"]["date_of_service"] == "2024-01-15"
    assert fake_groq.calls == []
    claim = await test_db.claims.find_one({"_id": data["claim_id"]})
    assert claim["extraction_source"] == "mock"


# --- Input limit -----------------------------------------------------------------------------


async def test_long_documents_are_truncated_to_the_configured_limit(
    async_client, test_db, fake_groq, monkeypatch, caplog
):
    monkeypatch.setattr(settings, "EXTRACTION_MAX_INPUT_CHARS", 600)
    long_text = "Patient: John Doe. " + "Itemised line. " * 200 + "Hospital: Hidden At The End."
    await test_db.documents.update_one({"_id": "doc-test-001"}, {"$set": {"extracted_text": long_text}})
    fake_groq.respond({"patient_name": "John Doe"})

    with caplog.at_level(logging.WARNING):
        response = await async_client.post("/api/extract/doc-test-001")

    assert response.json()["input_truncated"] is True
    user_message = fake_groq.calls[0]["messages"][1]["content"]
    assert "Hidden At The End" not in user_message
    assert "EXTRACTION_MAX_INPUT_CHARS" in caplog.text


# --- Preconditions ----------------------------------------------------------------------------


async def test_extract_document_not_found(async_client):
    response = await async_client.post("/api/extract/nonexistent")
    assert response.status_code == 404


async def test_extract_failed_document_explains_why(async_client, test_db, fake_groq):
    await test_db.documents.update_one(
        {"_id": "doc-test-001"},
        {"$set": {"processing_status": "failed", "extracted_text": "", "error_message": "No text found"}},
    )
    response = await async_client.post("/api/extract/doc-test-001")
    assert response.status_code == 400
    assert "Text extraction failed" in response.json()["detail"]
    assert fake_groq.calls == []


async def test_get_extraction_results_with_claim(async_client):
    response = await async_client.get("/api/extract/doc-test-002/results")
    assert response.status_code == 200

    data = response.json()
    assert data["extracted"] is True
    assert data["claim"]["id"] == "claim-test-001"


async def test_get_extraction_results_not_extracted(async_client):
    response = await async_client.get("/api/extract/doc-test-001/results")
    assert response.status_code == 200

    data = response.json()
    assert data["extracted"] is False
    assert data["claim"] is None
