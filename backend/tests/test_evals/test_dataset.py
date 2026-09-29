"""The evaluation dataset is deterministic, internally consistent and renders faithfully."""

import json
import re
from collections import Counter

import numpy as np
import pymupdf
import pytest

from evals.dataset import render
from evals.dataset.documents import document_text
from evals.dataset.generate import ground_truth
from models.extraction import CLAIM_FIELDS
from services.ocr_service import DOCUMENT_CLASSES
from utils.pdf_parser import read_pdf


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def dataset():
    files = ground_truth()
    return {path.name: (path, content, json.loads(content)) for path, content in files.items()}


def test_committed_ground_truth_matches_a_fresh_build(dataset):
    """Regenerate with `python -m evals.dataset.generate` after changing the generator."""
    for name, (path, content, _) in dataset.items():
        assert path.read_text() == content, f"{name} is out of date"


def test_documents_cover_the_three_families(dataset):
    documents = dataset["documents.json"][2]["documents"]
    assert len(documents) == 60
    assert Counter(doc["kind"] for doc in documents) == {
        "invoice": 24, "medical_report": 12, "discharge_summary": 12, "policy_summary": 12,
    }
    assert {doc["document_class"] for doc in documents} <= set(DOCUMENT_CLASSES)
    assert all(set(doc["fields"]) == set(CLAIM_FIELDS) for doc in documents)
    assert len({doc["id"] for doc in documents}) == 60


def test_printed_field_values_appear_in_the_document(dataset):
    for doc in dataset["documents.json"][2]["documents"]:
        text = normalize_whitespace(document_text(doc))
        for name, value in doc["printed"].items():
            assert (value is None) == (doc["fields"][name] is None)
            if value is not None:
                assert normalize_whitespace(str(value)) in text, (doc["id"], name)


def test_every_answerable_question_is_answered_by_its_source_document(dataset):
    documents = {doc["id"]: doc for doc in dataset["documents.json"][2]["documents"]}
    questions = dataset["qa.json"][2]["questions"]
    assert len(questions) >= 100
    assert Counter(q["style"] for q in questions if q["answerable"]) == {
        "identifier": 96, "descriptive": 72, "paraphrase": 48,
    }
    for question in questions:
        (source,) = question["source_document_ids"]
        text = normalize_whitespace(document_text(documents[source]))
        if question["answerable"]:
            assert normalize_whitespace(question["answer_text"]) in text, question["id"]
        else:  # invoices state no deductible; discharge summaries state no amounts
            assert question["answer"] is None
            if documents[source]["kind"] == "invoice":
                assert "deductible" not in text.lower()
            else:
                assert "$" not in text


def test_identifiers_follow_the_fictional_conventions(dataset):
    documents = dataset["documents.json"][2]["documents"]
    text = "\n".join(document_text(doc) for doc in documents)
    assert all("fictional" in page for doc in documents for page in doc["pages"])
    assert not re.search(r"\bNPI\b", text)
    assert set(re.findall(r"\(555\) (\d{2})", text)) == {"01"}
    assert all(doc["fields"]["provider_id"] is None or doc["fields"]["provider_id"].startswith("PRV-")
               for doc in documents)


def test_risk_claims_are_labelled(dataset):
    risk = dataset["risk_claims.json"][2]
    labels = Counter(case["anomalous"] for case in risk["claims"])
    assert labels == {False: 120, True: 86}
    assert len(risk["history"]) == 60
    types = Counter(anomaly["type"] for case in risk["claims"] for anomaly in case["anomalies"])
    assert set(types) == {"duplicate", "cost_outlier", "date_inconsistency", "missing_fields"}


def test_text_pdfs_read_back_as_the_ground_truth_and_scans_have_no_text_layer(dataset, tmp_path):
    doc = next(d for d in dataset["documents.json"][2]["documents"] if d["kind"] == "discharge_summary")
    text_pdf, scan_a, scan_b = tmp_path / "doc.pdf", tmp_path / "scan_a.pdf", tmp_path / "scan_b.pdf"

    render.render_text_pdf(doc["pages"], text_pdf)
    paged = read_pdf(str(text_pdf), max_pages=50)
    assert normalize_whitespace(paged.text) == normalize_whitespace(document_text(doc))
    assert len(paged.page_starts) == 2

    render.render_scanned_pdf(text_pdf, scan_a, seed=7)
    render.render_scanned_pdf(text_pdf, scan_b, seed=7)
    with pymupdf.open(str(scan_a)) as first, pymupdf.open(str(scan_b)) as second:
        assert first.page_count == 2
        assert all(not page.get_text().strip() for page in first)
        pixels = [np.frombuffer(d[0].get_pixmap(dpi=40).samples, dtype=np.uint8) for d in (first, second)]
        assert np.array_equal(*pixels)  # the same seed renders the same scan
