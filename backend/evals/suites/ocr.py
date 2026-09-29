"""
OCR suite (needs the tesseract binary; skipped when it is not installed).

Every document is read twice through the application's utils.pdf_parser:
the text PDF (text layer, no OCR) and its scanned variant (image-only, so
each page is rendered at 300 dpi and read by Tesseract). Character and word
error rates compare the result with the ground-truth text after collapsing
whitespace. field_values_found is the share of printed extraction-field
values (policy numbers, amounts, dates, names...) that appear verbatim in
the extracted text, a proxy for what extraction can recover.
"""

from collections import defaultdict
from typing import Any

from evals.common import Context, document_text, skipped
from evals.metrics import character_error_rate, normalize_whitespace, summarize, word_error_rate

NAME = "ocr"


def _found(doc: dict[str, Any], text: str) -> tuple[int, int]:
    haystack = normalize_whitespace(text)
    values = [str(value) for value in doc["printed"].values() if value is not None]
    return sum(1 for value in values if normalize_whitespace(value) in haystack), len(values)


def run(ctx: Context) -> dict[str, Any]:
    from utils.pdf_parser import tesseract_available

    if not tesseract_available():
        return skipped(NAME, "tesseract is not installed (for example: apt-get install tesseract-ocr)")

    text_layer = ctx.text_layer
    scanned = ctx.scanned_text()
    variants: dict[str, dict[str, list]] = {"text_layer": defaultdict(list), "scanned": defaultdict(list)}
    by_type: dict[str, list[float]] = defaultdict(list)
    found = {"text_layer": [0, 0], "scanned": [0, 0]}
    rows = []
    pages = 0
    for doc in ctx.documents:
        truth = document_text(doc)
        pages += len(doc["pages"])
        row = {"id": doc["id"], "kind": doc["kind"]}
        for variant, paged in (("text_layer", text_layer[doc["id"]]), ("scanned", scanned[doc["id"]])):
            cer = character_error_rate(truth, paged.text)
            variants[variant]["cer"].append(cer)
            variants[variant]["wer"].append(word_error_rate(truth, paged.text))
            hits, total = _found(doc, paged.text)
            found[variant][0] += hits
            found[variant][1] += total
            row[f"{variant}_cer"] = round(cer, 4)
        by_type[doc["kind"]].append(row["scanned_cer"])
        rows.append(row)

    metrics: dict[str, Any] = {}
    for variant, values in variants.items():
        metrics[variant] = {
            "cer": summarize(values["cer"]),
            "wer": summarize(values["wer"]),
            "field_values_found": round(found[variant][0] / found[variant][1], 4),
        }
    metrics["scanned"]["cer_by_type"] = {kind: summarize(values)["mean"] for kind, values in sorted(by_type.items())}
    ocr_seconds = sum(ctx.ocr_seconds.values())
    metrics["scanned"]["seconds_per_page"] = round(ocr_seconds / pages, 2) if ctx.ocr_seconds else None
    return {
        "suite": NAME,
        "status": "ok",
        "config": {"documents": len(ctx.documents), "pages": pages, "scan": "200 dpi JPEG, up to 1.5 degrees "
                   "rotation, Gaussian noise; read back at 300 dpi"},
        "metrics": metrics,
        "details": {"documents": rows},
    }


def summary(result: dict[str, Any]) -> list[str]:
    m, c = result["metrics"], result["config"]
    lines = [
        f"{c['documents']} documents ({c['pages']} pages). Scanned variants: {c['scan']}.",
        "",
        "| Path | CER mean | CER median | CER p90 | CER max | WER mean | Field values found |",
        "|---|---|---|---|---|---|---|",
    ]
    for variant, label in (("text_layer", "text layer (PyMuPDF)"), ("scanned", "scanned (Tesseract)")):
        cer, wer = m[variant]["cer"], m[variant]["wer"]
        lines.append(f"| {label} | {cer['mean']:.4f} | {cer['median']:.4f} | {cer['p90']:.4f} | {cer['max']:.4f} "
                     f"| {wer['mean']:.4f} | {m[variant]['field_values_found']:.3f} |")
    by_type = ", ".join(f"{kind} {value:.4f}" for kind, value in m["scanned"]["cer_by_type"].items())
    lines += ["", f"Scanned CER by document type: {by_type}."]
    if m["scanned"].get("seconds_per_page") is not None:
        lines.append(f"OCR time: {m['scanned']['seconds_per_page']} s per page.")
    return lines
