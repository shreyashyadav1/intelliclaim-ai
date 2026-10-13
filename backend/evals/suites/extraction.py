"""
Extraction suite (needs GROQ_API_KEY; skipped when it is not set).

Runs the application's ExtractionService (Groq JSON mode, GROQ_MODEL) on
every document's text, as the upload path would produce it: from the text
PDF and, when tesseract is installed, from the scanned PDF via OCR. The
document class passed along is the keyword classifier's, as in the Groq
deployment.

Per field: precision/recall/F1 with the lenient comparison and exact match
with the strict one (see evals/matching.py); a value where the ground truth
has none is a false positive. Also: documents with all eleven fields
exactly right, request latency p50/p95, tokens and estimated cost per
document (EVAL_GROQ_*_USD_PER_MTOK).
"""

from typing import Any

from evals.common import Context, skipped
from evals.matching import field_matches
from evals.metrics import field_counts, latency_summary

NAME = "extraction"


async def _extract_all(docs: list[dict[str, Any]], texts: dict[str, str]) -> dict[str, Any]:
    from evals.llm_support import groq_only, usage_summary, with_retries
    from models.extraction import CLAIM_FIELDS
    from services.extraction_service import ExtractionService
    from services.llm import LLMError
    from services.ocr_service import OCRService

    extractor, classifier = ExtractionService(), OCRService()
    rows = []
    async with groq_only() as recorder:
        for doc in docs:
            text = texts[doc["id"]]
            document_class = classifier._classify_with_keywords(text)
            try:
                result = await with_retries(lambda text=text, cls=document_class:
                                            extractor.extract_claim_data(text, cls))
            except LLMError as exc:
                rows.append({"id": doc["id"], "error": exc.detail})
                continue
            rows.append({"id": doc["id"], "source": result.source, "predicted": result.fields.model_dump()})

    by_id = {doc["id"]: doc for doc in docs}
    succeeded = [row for row in rows if "predicted" in row]
    per_field: dict[str, Any] = {}
    all_triples = []
    for name in CLAIM_FIELDS:
        triples = []
        exact = 0
        for row in succeeded:
            expected, predicted = by_id[row["id"]]["fields"][name], row["predicted"][name]
            triples.append((expected, predicted, field_matches(name, expected, predicted)))
            exact += field_matches(name, expected, predicted, strict=True)
        per_field[name] = {**field_counts(triples), "exact_match": round(exact / len(succeeded), 4) if succeeded else 0}
        all_triples += triples
    document_exact = sum(
        all(field_matches(name, by_id[row["id"]]["fields"][name], row["predicted"][name], strict=True)
            for name in CLAIM_FIELDS)
        for row in succeeded
    )
    return {
        "documents": len(docs),
        "failures": len(rows) - len(succeeded),
        "micro": field_counts(all_triples),
        "document_exact_match": round(document_exact / len(succeeded), 4) if succeeded else 0,
        "per_field": per_field,
        "latency": latency_summary([call.seconds for call in recorder.calls]),
        "usage": usage_summary(recorder.calls, len(docs)),
        "rows": rows,
    }


async def run(ctx: Context) -> dict[str, Any]:
    from config import settings
    from evals.llm_support import KEY_MISSING, groq_configured
    from utils.pdf_parser import tesseract_available

    if not groq_configured():
        return skipped(NAME, "MOCK_LLM is on" if settings.MOCK_LLM else KEY_MISSING)

    docs = ctx.documents[: ctx.limit]
    metrics: dict[str, Any] = {}
    details: dict[str, Any] = {}
    notes = []
    variants = {"text_pdf": {doc["id"]: ctx.text_layer[doc["id"]].text for doc in docs}}
    if tesseract_available():
        scanned = ctx.scanned_text()
        variants["scanned_pdf"] = {doc["id"]: scanned[doc["id"]].text for doc in docs}
    else:
        notes.append("Scanned PDFs not evaluated: tesseract is not installed.")

    for variant, texts in variants.items():
        result = await _extract_all(docs, texts)
        details[variant] = result.pop("rows")
        metrics[variant] = result
    return {
        "suite": NAME,
        "status": "ok",
        "config": {"model": settings.GROQ_MODEL, "documents": len(docs),
                   "max_input_chars": settings.EXTRACTION_MAX_INPUT_CHARS},
        "metrics": metrics,
        "notes": notes,
        "details": details,
    }


def summary(result: dict[str, Any]) -> list[str]:
    c = result["config"]
    lines = [f"{c['documents']} documents, Groq {c['model']} (JSON mode).", ""]
    for variant, m in result["metrics"].items():
        micro, latency, usage = m["micro"], m["latency"], m["usage"]
        lines += [
            f"**{variant}**: micro precision {micro['precision']:.3f}, recall {micro['recall']:.3f}, "
            f"F1 {micro['f1']:.3f}; all 11 fields exact in {m['document_exact_match']:.3f} of documents; "
            f"{m['failures']} failed requests.",
            f"Latency p50 {latency.get('p50_ms')} ms, p95 {latency.get('p95_ms')} ms; "
            f"{usage['prompt_tokens_per_item']} prompt + {usage['completion_tokens_per_item']} completion tokens "
            f"and ${usage['cost_usd_per_item']:.5f} per document (at ${usage['price_usd_per_mtok']['input']}/"
            f"${usage['price_usd_per_mtok']['output']} per million tokens).",
            "",
            "| Field | Precision | Recall | F1 | Exact match |",
            "|---|---|---|---|---|",
        ]
        for name, row in m["per_field"].items():
            lines.append(f"| {name} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} "
                         f"| {row['exact_match']:.3f} |")
        lines.append("")
    lines += [f"_{note}_" for note in result.get("notes", [])]
    return lines
