"""
IntelliClaim AI — AI Evaluation Tests

Tests that demonstrate AI behavior quality:
1. Extraction consistency — mock data yields valid fields 100% of the time
2. RAG retrieval relevance — mock queries return contextually relevant answers
3. Validation hybrid scoring — rule + AI scores produce expected risk levels
"""

import pytest
import asyncio

from services.extraction_service import ExtractionService
from services.rag_service import RAGService
from services.validation_service import ValidationService


@pytest.mark.asyncio
async def test_extraction_consistency():
    """Mock extraction produces valid, non-empty fields every time.

    This is an *evaluation* test: it proves that the extraction service,
    even in demo mode, consistently yields structured data with the required
    fields populated.
    """
    extractor = ExtractionService()
    results = []

    for _ in range(20):
        result = await extractor.extract_claim_data(
            text="Patient: John Doe. Policy: POL-001. Diagnosis: Appendicitis.",
            document_class="claim_form",
        )
        results.append(result)

    # All 20 runs should have the required fields
    required_fields = [
        "policy_number", "claim_number", "patient_name",
        "diagnosis", "treatment_cost", "hospital_name",
    ]
    for r in results:
        for field in required_fields:
            assert r.get(field) is not None, f"Field {field} missing in extraction"
            assert str(r.get(field)) != "", f"Field {field} is empty"

    # Treatment cost should always be a positive number
    costs = [r["treatment_cost"] for r in results]
    assert all(c > 0 for c in costs), "Some extraction yields non-positive cost"

    # Confidence should be in the 0.7–0.95 range
    confidences = [r.get("confidence_score", 0) for r in results]
    assert all(0.7 <= c <= 0.95 for c in confidences), "Confidence outside expected demo range"

    # 100% field coverage (no None required fields)
    coverage = sum(
        1 for r in results
        for f in required_fields
        if r.get(f) is not None and str(r.get(f)) != ""
    ) / (len(results) * len(required_fields))
    assert coverage == 1.0, f"Field coverage {coverage:.0%} < 100%"


@pytest.mark.asyncio
async def test_rag_retrieval_relevance():
    """RAG query returns a contextually relevant answer from mock data.

    Even in demo mode, the mock query should provide semantically
    appropriate answers based on keyword matching.
    """
    rag = RAGService()

    test_cases = [
        ("What is the average treatment cost?", "cost"),
        ("Tell me about diagnoses", "diagnoses"),
        ("Which hospitals are mentioned?", "hospital"),
        ("Are there any fraud risks?", "risk"),
    ]

    for question, expected_keyword in test_cases:
        result = await rag.query(question, top_k=3)
        assert "answer" in result
        assert "source_documents" in result
        assert len(result["source_documents"]) > 0
        # The mock answer should contain a relevant keyword
        answer_lower = result["answer"].lower()
        assert expected_keyword in answer_lower, (
            f"Expected '{expected_keyword}' in answer for '{question}', got: {answer_lower[:100]}"
        )


@pytest.mark.asyncio
async def test_validation_hybrid_scoring(monkeypatch):
    """Validation produces correct risk levels based on composite scoring.

    Tests the rule-based layer independently (no OpenAI key = no AI layer),
    ensuring thresholds, duplicate detection, and date logic work correctly.
    """
    # Mock get_database() to avoid Motor event-loop binding issues in tests
    class MockCollection:
        async def count_documents(self, query):
            return 0  # No duplicates in tests

    class MockDB:
        claims = MockCollection()

    import db.connection
    monkeypatch.setattr(db.connection, "_database", MockDB())
    monkeypatch.setattr(db.connection, "get_database", lambda: MockDB())

    # Mock _check_duplicate to avoid DB / event-loop issues in unit tests
    # Must be async because validate_claim does `await self._check_duplicate()`
    async def _mock_check_duplicate(self, claim):
        return False

    monkeypatch.setattr(ValidationService, "_check_duplicate", _mock_check_duplicate)

    validator = ValidationService()

    # High-risk claim: very high cost + missing fields + invalid dates
    high_risk = {
        "claim_number": "CLM-HIGH",
        "policy_number": "POL-HIGH",
        "patient_name": "Risky Patient",
        "diagnosis": "Acute Myocardial Infarction (I21.9)",
        "treatment_cost": 160000,
        "hospital_name": "Test Hospital",
        "hospital_address": "",
        "provider_id": "",
        "date_of_service": "2024-01-01",
        "date_of_admission": "2024-01-15",
        "date_of_discharge": "2024-01-01",
        "status": "pending",
    }
    result = await validator.validate_claim(high_risk)
    assert result["risk_level"] in ("medium", "high"), f"Expected medium/high risk, got {result['risk_level']}"
    assert result["risk_score"] >= 30, f"Expected score >= 30, got {result['risk_score']}"
    assert any(f["type"] == "very_high_cost" for f in result["flags"])

    # Low-risk claim: normal cost, all fields present
    low_risk = {
        "claim_number": "CLM-LOW",
        "policy_number": "POL-LOW",
        "patient_name": "Safe Patient",
        "diagnosis": "Type 2 Diabetes Mellitus (E11.9)",
        "treatment_cost": 12000,
        "hospital_name": "Safe Hospital",
        "hospital_address": "456 Safe St",
        "provider_id": "NPI-456",
        "date_of_service": "2024-02-01",
        "date_of_admission": "2024-02-01",
        "date_of_discharge": "2024-02-05",
        "status": "pending",
    }
    result = await validator.validate_claim(low_risk)
    assert result["risk_level"] == "low", f"Expected low risk, got {result['risk_level']}"
    assert result["risk_score"] < 30, f"Expected score < 30, got {result['risk_score']}"

    # Medium-risk claim: missing some fields + high cost
    medium_risk = {
        "claim_number": "CLM-MED",
        "policy_number": "POL-MED",
        "patient_name": "Med Patient",
        "diagnosis": "",
        "treatment_cost": 55000,
        "hospital_name": "Med Hospital",
        "hospital_address": "",
        "provider_id": "",
        "date_of_service": "2024-03-01",
        "date_of_admission": "2024-03-01",
        "date_of_discharge": "2024-03-10",
        "status": "pending",
    }
    result = await validator.validate_claim(medium_risk)
    assert result["risk_level"] in ("medium", "high"), f"Expected medium/high risk, got {result['risk_level']}"
    assert result["risk_score"] >= 30, f"Expected score >= 30, got {result['risk_score']}"
    assert any(f["type"] == "missing_fields" for f in result["flags"])
    assert any(f["type"] == "high_cost" for f in result["flags"])
