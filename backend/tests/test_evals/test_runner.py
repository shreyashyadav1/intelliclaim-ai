"""Tests for the evaluation runner and the suites (LLM suites run against FakeGroq)."""

import json

import pytest

import evals.dataset.render as render
from config import Settings, settings
from evals import run as runner
from evals.common import Context
from evals.suites import classification, extraction, ocr, rag_answer, risk
from services import llm


@pytest.fixture
def rendered_to_tmp(tmp_path, monkeypatch):
    """Render dataset PDFs into a temporary directory instead of evals/data/generated."""
    monkeypatch.setattr(render, "TEXT_DIR", tmp_path / "text")
    monkeypatch.setattr(render, "SCANNED_DIR", tmp_path / "scanned")
    monkeypatch.setattr(render, "MANIFEST", tmp_path / "manifest.json")
    return tmp_path


@pytest.fixture
def groq_client(monkeypatch, fake_groq):
    """The suites create their own Groq client; hand them the fake."""
    monkeypatch.setattr(llm, "_create_groq_client", lambda: fake_groq)
    return fake_groq


# --- Runner -----------------------------------------------------------------------------------


def test_suite_groups_expand_without_duplicates():
    assert runner.selected_suites(["offline"]) == ["retrieval", "ocr", "classification", "risk"]
    assert runner.selected_suites(["risk", "offline"]) == ["risk", "retrieval", "ocr", "classification"]
    assert runner.selected_suites(["all"])[-2:] == ["extraction", "rag-answer"]


def test_thresholds_fail_on_low_metrics_missing_metrics_and_skipped_suites():
    results = {
        "retrieval": {"status": "ok", "metrics": {"hybrid": {"recall@5": 0.9, "mrr": 0.7}}},
        "ocr": {"status": "skipped", "reason": "tesseract is not installed"},
    }
    thresholds = {
        "_comment": "ignored",
        "retrieval": {"hybrid.recall@5": {"min": 0.95}, "hybrid.mrr": {"min": 0.6}, "vector.mrr": {"min": 0.1}},
        "ocr": {"scanned.cer.mean": {"max": 0.05}},
        "risk": {"rules.pr_auc": {"min": 0.5}},
    }
    failures = runner.check_thresholds(results, thresholds, ["retrieval", "ocr"])
    assert failures == [
        "retrieval: hybrid.recall@5 = 0.9 is below the minimum 0.95",
        "retrieval: metric vector.mrr is missing",
        "ocr: has thresholds but did not run (tesseract is not installed)",
    ]


def test_run_writes_results_and_a_summary(tmp_path, rendered_to_tmp):
    output = tmp_path / "out"
    assert runner.main(["--suite", "classification", "--output-dir", str(output)]) == 0

    results = json.loads((output / "results.json").read_text())
    assert results["run"]["command"] == f"python -m evals.run --suite classification --output-dir {output}"
    assert results["suites"]["classification"]["metrics"]["keyword"]["accuracy"] > 0
    summary = (output / "summary.md").read_text()
    assert "## classification" in summary and "Confusion matrix" in summary


def test_run_exits_1_when_thresholds_are_missed(tmp_path, rendered_to_tmp):
    thresholds = tmp_path / "thresholds.json"
    thresholds.write_text(json.dumps({"classification": {"keyword.accuracy": {"min": 1.01}}}))
    code = runner.main(["--suite", "classification", "--output-dir", str(tmp_path / "out"),
                        "--check-thresholds", str(thresholds)])
    assert code == 1
    assert "FAIL: classification: keyword.accuracy" in (tmp_path / "out" / "summary.md").read_text()


# --- Suites -------------------------------------------------------------------------------------


async def test_classification_keyword_path(rendered_to_tmp):
    result = await classification.run(Context())
    report = result["metrics"]["keyword"]
    assert report["per_class"]["invoice"]["support"] == 24
    assert "llm" not in result["metrics"]
    assert result["notes"]


def test_ocr_suite_compares_scans_with_the_text_layer(rendered_to_tmp, monkeypatch):
    import utils.pdf_parser as pdf_parser

    monkeypatch.setattr(pdf_parser, "tesseract_available", lambda: True)
    monkeypatch.setattr(pdf_parser, "_ocr", lambda image: "Unreadable scan with nothing useful in it")
    ctx = Context()
    ctx.__dict__["documents"] = ctx.documents[:3]  # three documents keep the test fast

    result = ocr.run(ctx)

    m = result["metrics"]
    assert m["text_layer"]["cer"]["mean"] == 0.0 and m["text_layer"]["field_values_found"] == 1.0
    assert m["scanned"]["cer"]["mean"] > 0.5 and m["scanned"]["field_values_found"] == 0.0
    assert sum(m["scanned"]["missed_values_by_field"].values()) > 0
    assert "Printed field values not recovered" in "\n".join(ocr.summary(result))


async def test_risk_suite_scores_rules_against_labels(test_db):
    result = await risk.run(Context())
    rules = result["metrics"]["rules"]
    assert result["status"] == "ok"
    assert rules["claims"] == {"scored": 206, "anomalous": 86, "clean": 120, "errors": 0}
    assert rules["rule_detection_rate"]["duplicate/exact"]["rate"] == 1.0
    assert rules["rule_detection_rate"]["duplicate/name_typo"]["rate"] == 0.0
    assert 0 < rules["pr_auc"] <= 1
    assert {"5", "10", "15", "20", "25", "30", "40", "50", "60"} <= set(rules["thresholds"])
    best = rules["best_f1"]
    assert best["f1"] == max(row["f1"] for row in rules["thresholds"].values())
    assert "Highest F1 over every observed score" in "\n".join(risk.summary(result))
    # RISK_FLAG_THRESHOLD's default was chosen by this rule; recalibrate it if the rules change.
    assert best["threshold"] == Settings.model_fields["RISK_FLAG_THRESHOLD"].default
    assert rules["flagged"]["threshold"] == settings.RISK_FLAG_THRESHOLD


async def test_llm_suites_skip_without_a_key():
    for suite in (extraction, rag_answer):
        result = await suite.run(Context())
        assert result["status"] == "skipped"
        assert "GROQ_API_KEY" in result["reason"]


async def test_extraction_suite_scores_fields_tokens_and_cost(rendered_to_tmp, groq_client, monkeypatch):
    import utils.pdf_parser as pdf_parser

    monkeypatch.setattr(pdf_parser, "tesseract_available", lambda: False)
    ctx = Context(limit=2)
    first, second = ctx.documents[:2]
    groq_client.respond(first["fields"], {**second["fields"], "patient_name": "Someone Else"})

    result = await extraction.run(ctx)

    m = result["metrics"]["text_pdf"]
    assert m["documents"] == 2 and m["failures"] == 0
    assert m["per_field"]["policy_number"]["f1"] == 1.0
    assert m["per_field"]["patient_name"]["exact_match"] == 0.5
    assert m["usage"]["prompt_tokens_per_item"] == 100  # FakeGroq reports 100 prompt tokens per request
    assert m["usage"]["cost_usd_per_item"] > 0
    assert m["latency"]["n"] == 2
    assert result["notes"] == ["Scanned PDFs not evaluated: tesseract is not installed."]


async def test_rag_answer_suite_scores_answers_citations_and_abstentions(rendered_to_tmp, groq_client):
    ctx = Context(limit=3)
    replies = []
    for question in ctx.questions[:3]:
        replies.append(f"{question['answer_text']} [1]" if question["answerable"] else "Not stated.")
    groq_client.respond(*replies)

    result = await rag_answer.run(ctx)

    m = result["metrics"]
    assert m["questions"]["asked"] == 3 and m["questions"]["errors"] == 0
    assert 0 <= m["answer_accuracy"] <= 1
    assert m["usage"]["requests"] == 3
    rows = result["details"]["questions"]
    assert all("answer" in row for row in rows)
