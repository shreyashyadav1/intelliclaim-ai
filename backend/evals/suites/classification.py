"""
Classification suite.

Classifies the text layer of every document with the application's keyword
classifier (the path used whenever OPENAI_API_KEY is not set, including the
Groq deployment) and reports accuracy, per-class precision/recall/F1 and the
confusion matrix against the ground-truth labels.

The application classifies with an LLM only when OPENAI_API_KEY is set; the
LLM path is then evaluated as well. Policy summaries are labelled
"policy_document".
"""

from typing import Any

from evals.common import Context
from evals.metrics import classification_report

NAME = "classification"


async def run(ctx: Context) -> dict[str, Any]:
    from config import settings
    from services.llm import LLMError
    from services.ocr_service import DOCUMENT_CLASSES, OCRService

    service = OCRService()
    texts = {doc["id"]: ctx.text_layer[doc["id"]].text for doc in ctx.documents}
    y_true = [doc["document_class"] for doc in ctx.documents]
    keyword = [service._classify_with_keywords(texts[doc["id"]]) for doc in ctx.documents]
    metrics: dict[str, Any] = {"keyword": classification_report(y_true, keyword, DOCUMENT_CLASSES)}
    notes = []
    misclassified = [
        {"id": doc["id"], "kind": doc["kind"], "true": truth, "keyword": prediction}
        for doc, truth, prediction in zip(ctx.documents, y_true, keyword, strict=True)
        if truth != prediction
    ]

    if settings.has_openai_key and not settings.MOCK_LLM:
        predictions, failures = [], 0
        for doc in ctx.documents[: ctx.limit]:
            try:
                predictions.append(await service._classify_with_openai(texts[doc["id"]]))
            except LLMError:
                failures += 1
                predictions.append("other")
        truth = y_true[: len(predictions)]
        metrics["llm"] = {**classification_report(truth, predictions, DOCUMENT_CLASSES), "failures": failures,
                          "model": settings.OPENAI_MODEL}
    else:
        notes.append("LLM classification not run: the application classifies with an LLM only when "
                     "OPENAI_API_KEY is set (the Groq configuration uses the keyword classifier).")

    return {
        "suite": NAME,
        "status": "ok",
        "config": {"documents": len(ctx.documents), "labels": list(DOCUMENT_CLASSES)},
        "metrics": metrics,
        "notes": notes,
        "details": {"misclassified_by_keywords": misclassified},
    }


def _report(lines: list[str], name: str, report: dict[str, Any]) -> None:
    lines += [f"**{name}**: accuracy {report['accuracy']:.3f}, macro F1 {report['macro_f1']:.3f}", "",
              "| Class | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
    for label, row in report["per_class"].items():
        lines.append(f"| {label} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} | {row['support']} |")
    labels = report["confusion_matrix"]["labels"]
    lines += ["", "Confusion matrix (rows: true class, columns: predicted):", "",
              "| true \\ predicted | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    for label, row in zip(labels, report["confusion_matrix"]["matrix"], strict=True):
        lines.append(f"| {label} | " + " | ".join(str(value) for value in row) + " |")
    lines.append("")


def summary(result: dict[str, Any]) -> list[str]:
    lines = [f"{result['config']['documents']} documents (text layer).", ""]
    _report(lines, "Keyword classifier", result["metrics"]["keyword"])
    if "llm" in result["metrics"]:
        _report(lines, f"LLM classifier ({result['metrics']['llm']['model']})", result["metrics"]["llm"])
    lines += [f"_{note}_" for note in result.get("notes", [])]
    return lines
