"""Tests for rule-based checks, AI review parsing and composite scoring."""

import pytest

import db.connection as db_conn
from services.llm import LLMOutputError, LLMProviderError
from services.validation_service import AI, RULE, ValidationService

validator = ValidationService()

CLEAN_CLAIM = {
    "_id": "claim-clean",
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


@pytest.fixture
async def database(test_db, monkeypatch):
    monkeypatch.setattr(db_conn, "_database", test_db)
    return test_db


@pytest.fixture
def no_duplicates(monkeypatch):
    async def _never(self, claim):
        return False

    monkeypatch.setattr(ValidationService, "_check_duplicate", _never)


def _types(result: dict) -> list[str]:
    return [flag["type"] for flag in result["flags"]]


# --- Rule-based scoring (no AI provider configured) --------------------------------


async def test_rule_based_risk_levels(no_duplicates):
    high = {
        **CLEAN_CLAIM,
        "treatment_cost": 160000,
        "date_of_admission": "2024-01-15",
        "date_of_discharge": "2024-01-01",
    }
    result = await validator.validate_claim(high)
    assert result["risk_score"] == 50.0  # very_high_cost (25) + invalid_dates (25)
    assert result["risk_level"] == "medium"
    assert {"very_high_cost", "invalid_dates"} <= set(_types(result))

    low = await validator.validate_claim(CLEAN_CLAIM)
    assert low["risk_score"] == 0.0
    assert low["risk_level"] == "low"

    medium = await validator.validate_claim({**CLEAN_CLAIM, "diagnosis": "", "treatment_cost": 55000})
    assert medium["risk_score"] == 30.0  # missing_fields (15) + high_cost (15)
    assert medium["risk_level"] == "medium"


async def test_every_rule_flag_is_marked_as_rule(no_duplicates):
    result = await validator.validate_claim({**CLEAN_CLAIM, "treatment_cost": 60000})
    assert result["flags"] and all(flag["origin"] == RULE for flag in result["flags"])


async def test_without_provider_ai_review_is_reported_as_not_configured(no_duplicates):
    review = (await validator.validate_claim(CLEAN_CLAIM))["ai_review"]
    assert review["status"] == "not_configured"
    assert review["source"] is None
    assert review["ai_summary"] == "AI review not available (no API key configured)."


async def test_mock_mode_skips_the_provider(no_duplicates, mock_llm, fake_groq):
    review = (await validator.validate_claim(CLEAN_CLAIM))["ai_review"]
    assert review["status"] == "mock"
    assert review["source"] == "mock"
    assert fake_groq.calls == []


# --- Duplicates are counted once --------------------------------------------------------


async def test_duplicate_adds_one_high_flag_worth_25(monkeypatch):
    """Duplicates used to score 45: the high-severity flag (25) plus a separate +20 penalty."""

    async def _always(self, claim):
        return True

    monkeypatch.setattr(ValidationService, "_check_duplicate", _always)
    result = await validator.validate_claim(CLEAN_CLAIM)
    assert result["is_duplicate"] is True
    assert _types(result) == ["duplicate_claim"]
    assert result["risk_score"] == 25.0


# --- AI flags are not double-counted ----------------------------------------------------


async def test_ai_flags_with_unexpected_types_only_count_through_the_ai_score(no_duplicates, fake_groq):
    """An AI flag typed e.g. "missing_info" used to add its severity weight on top of the AI score."""
    fake_groq.respond({
        "risk_flags": [
            {"type": "missing_info", "description": "No referral on file", "severity": "high", "confidence": 1.0},
            {"type": "Totally New Category!", "description": "Odd pattern", "severity": "high", "confidence": 1.0},
        ],
        "ai_risk_score": 50,
        "summary": "Two concerns.",
    })
    result = await validator.validate_claim(CLEAN_CLAIM)

    assert result["risk_score"] == 20.0  # 0 from rules + 50 x 0.4 x 1.0
    ai_flags = [flag for flag in result["flags"] if flag["origin"] == AI]
    assert [flag["type"] for flag in ai_flags] == ["missing_info", "totally_new_category"]
    assert result["ai_review"]["status"] == "completed"
    assert result["ai_review"]["source"] == "groq"
    assert result["ai_review"]["ai_flag_count"] == 2


async def test_ai_output_is_coerced_instead_of_crashing(no_duplicates, fake_groq):
    fake_groq.respond({
        "risk_flags": [
            {"type": "billing_anomaly", "description": "Upcoded", "severity": "CRITICAL", "confidence": "90%"},
            "A bare string flag",
            {"type": "no_description"},
            42,
        ],
        "ai_risk_score": "80",
        "summary": ["not", "a", "string"],
    })
    result = await validator.validate_claim(CLEAN_CLAIM)
    review = result["ai_review"]

    ai_flags = [flag for flag in result["flags"] if flag["origin"] == AI]
    assert [(f["severity"], f["confidence"]) for f in ai_flags] == [("high", 0.9), ("medium", 0.5)]
    assert review["ai_risk_score"] == 80.0
    assert review["ai_confidence"] == 0.7
    assert review["ai_summary"] == ""
    assert result["risk_score"] == 22.4  # 80 x 0.4 x 0.7


@pytest.mark.parametrize("score", ["high", None, [], {"x": 1}])
async def test_non_numeric_ai_score_counts_as_zero(no_duplicates, fake_groq, score):
    fake_groq.respond({"risk_flags": [], "ai_risk_score": score, "summary": "ok"})
    result = await validator.validate_claim(CLEAN_CLAIM)
    assert result["ai_review"]["ai_risk_score"] == 0.0
    assert result["risk_score"] == 0.0


async def test_ai_score_is_clamped(no_duplicates, fake_groq):
    fake_groq.respond({"risk_flags": [{"description": "x", "confidence": 3}], "ai_risk_score": 900})
    result = await validator.validate_claim(CLEAN_CLAIM)
    assert result["ai_review"]["ai_risk_score"] == 100.0
    assert result["ai_review"]["ai_confidence"] == 0.03  # 3 on a 0-100 scale


async def test_ai_output_without_review_keys_is_an_error(no_duplicates, fake_groq):
    fake_groq.respond({"verdict": "fine"})
    with pytest.raises(LLMOutputError):
        await validator.validate_claim(CLEAN_CLAIM)


async def test_provider_failure_propagates(no_duplicates, fake_groq, groq_errors):
    fake_groq.respond(groq_errors.connection())
    with pytest.raises(LLMProviderError):
        await validator.validate_claim(CLEAN_CLAIM)


# --- Robustness to bad stored data ------------------------------------------------------


@pytest.mark.parametrize(
    ("cost", "expected_types"),
    [
        ("$28,500", []),
        ("$160,000", ["very_high_cost"]),
        ("a lot", ["invalid_cost"]),
        ({"amount": 5}, ["invalid_cost"]),
        (0, ["zero_cost"]),
        (None, ["missing_fields"]),
    ],
)
async def test_non_numeric_costs_do_not_raise(no_duplicates, cost, expected_types):
    """A string cost used to raise TypeError (500) when compared with the thresholds."""
    result = await validator.validate_claim({**CLEAN_CLAIM, "treatment_cost": cost})
    assert _types(result) == expected_types


async def test_non_string_dates_are_a_format_flag(no_duplicates):
    result = await validator.validate_claim({**CLEAN_CLAIM, "date_of_admission": 20240101})
    assert _types(result) == ["date_format"]


async def test_placeholder_claim_number_counts_as_missing(no_duplicates):
    claim = {**CLEAN_CLAIM, "claim_number": "UNASSIGNED-ABC123", "claim_number_is_placeholder": True}
    result = await validator.validate_claim(claim)
    assert result["flags"][0]["description"] == "Missing required fields: claim_number"


def test_claim_summary_handles_missing_and_string_costs():
    assert "Treatment Cost: N/A" in validator._build_claim_summary({"treatment_cost": None})
    assert "Treatment Cost: $28,500.00" in validator._build_claim_summary({"treatment_cost": "28500"})


# --- Duplicate detection matches what it documents ----------------------------------------


async def test_duplicate_requires_same_patient_diagnosis_and_service_date(database):
    candidate = {
        "_id": "claim-new",
        "patient_name": "john doe",
        "diagnosis": "Acute Appendicitis (K35.80)",
        "date_of_service": "2024-01-15",
    }
    assert await validator._check_duplicate(candidate) is True
    assert await validator._check_duplicate({**candidate, "date_of_service": "2024-03-01"}) is False
    assert await validator._check_duplicate({**candidate, "patient_name": "John"}) is False
    assert await validator._check_duplicate({**candidate, "diagnosis": "Pneumonia"}) is False


async def test_duplicate_without_service_date_compares_patient_and_diagnosis(database):
    candidate = {"_id": "claim-new", "patient_name": "John Doe", "diagnosis": "Acute Appendicitis"}
    assert await validator._check_duplicate(candidate) is True


async def test_duplicate_check_ignores_the_claim_itself(database):
    existing = await database.claims.find_one({"_id": "claim-test-002"})
    assert await validator._check_duplicate(existing) is False


async def test_duplicate_check_escapes_regex_characters(database):
    assert await validator._check_duplicate({"patient_name": "(.*", "diagnosis": "[a-"}) is False


async def test_duplicate_flag_describes_what_was_compared(database):
    await database.claims.insert_one({
        "_id": "claim-copy", "claim_number": "CLM-COPY", "patient_name": "John Doe",
        "diagnosis": "Acute Appendicitis (K35.80)", "date_of_service": "2024-01-15",
    })
    original = await database.claims.find_one({"_id": "claim-test-002"})
    result = await validator.validate_claim(original)
    duplicate = next(flag for flag in result["flags"] if flag["type"] == "duplicate_claim")
    assert duplicate["description"].endswith("same patient, diagnosis and date of service")
