"""Document classification: keyword rules (no OpenAI key) and the LLM path's label check."""

import pytest

from services import llm
from services.ocr_service import DOCUMENT_CLASSES, OCRService

classifier = OCRService()

# Worded differently from the evaluation dataset's templates on purpose.
POLICY_CERTIFICATE = """
Harbourline Health Insurance
CERTIFICATE OF COVERAGE
Policyholder: Dana Whitfield        Policy number: HP-77120
Policy period: 01/01/2026 - 12/31/2026
Monthly premium: $412.00
Deductible: $1,500 per member, then 20% coinsurance
Exclusions: cosmetic procedures and experimental treatment
"""

CLAIM_FORM = """
HEALTH INSURANCE CLAIM FORM
Claimant: Dana Whitfield
Policyholder: Dana Whitfield        Policy number: HP-77120
Claim number: CLM-2026-55120
Reason for reimbursement: emergency room visit on 03/14/2026
Other coverage: none
Authorization: I authorize the release of medical information needed to process this claim.
"""


def test_policy_documents_have_their_own_class():
    assert "policy_document" in DOCUMENT_CLASSES
    assert classifier._classify_with_keywords(POLICY_CERTIFICATE) == "policy_document"


def test_claim_forms_that_name_the_policyholder_stay_claim_forms():
    assert classifier._classify_with_keywords(CLAIM_FORM) == "claim_form"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("INVOICE\nItemized charges\nSubtotal: $120.00\nTotal amount due: $120.00", "invoice"),
        ("DISCHARGE SUMMARY\nAdmission date: 2026-02-01\nDischarge date: 2026-02-04\nLength of stay: 3 days",
         "discharge_summary"),
        ("OUTPATIENT MEDICAL REPORT\nExamination findings: normal. Examining physician: Dr. Lee", "medical_report"),
        ("Grocery list: apples, bread, milk", "other"),
    ],
)
def test_other_classes_are_unchanged(text, expected):
    assert classifier._classify_with_keywords(text) == expected


async def test_llm_classifier_offers_and_accepts_the_policy_class(monkeypatch):
    prompts = []

    async def _fake_chat(messages, params):
        prompts.append(messages[0]["content"])
        return " Policy_Document \n"

    monkeypatch.setattr(llm, "openai_chat", _fake_chat)
    assert await classifier._classify_with_openai("Certificate of coverage") == "policy_document"
    assert "- policy_document" in prompts[0]


async def test_llm_classifier_maps_unknown_labels_to_other(monkeypatch):
    async def _fake_chat(messages, params):
        return "insurance_policy"

    monkeypatch.setattr(llm, "openai_chat", _fake_chat)
    assert await classifier._classify_with_openai("Certificate of coverage") == "other"
