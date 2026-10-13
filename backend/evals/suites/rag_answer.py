"""
RAG answer suite (needs GROQ_API_KEY; skipped when it is not set).

Indexes the text PDFs with the production defaults and asks every question
through the application's RAGService.query (retriever -> LCEL chain ->
ChatGroq with GROQ_MODEL), top_k=5, in RAG_RETRIEVAL_MODE (or
--retrieval-mode).

- Answer accuracy: the expected answer appears in the answer (normalised
  match by answer type, see evals/matching.py).
- Citation accuracy: the answer cites the source document (hit rate), and
  the share of cited documents that are sources (precision).
- Unanswerable questions: the model should reply that the documents do not
  contain the answer and cite nothing.
"""

import logging
import tempfile
from collections import defaultdict
from typing import Any

from evals.common import Context, skipped
from evals.matching import answer_matches, compact
from evals.metrics import latency_summary

NAME = "rag-answer"
TOP_K = 5
logger = logging.getLogger("evals.rag_answer")


def _rate(values: list[bool]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


async def run(ctx: Context) -> dict[str, Any]:
    from config import RAG_CHUNK_SIZE, settings
    from evals.llm_support import KEY_MISSING, groq_configured, groq_only, usage_summary, with_retries

    if not groq_configured():
        return skipped(NAME, "MOCK_LLM is on" if settings.MOCK_LLM else KEY_MISSING)

    from chromadb.api.shared_system_client import SharedSystemClient

    from evals.suites.retrieval import _build_index
    from services import rag_service as rag_module
    from services.llm import LLMError
    from services.rag_chain import NO_ANSWER

    questions = ctx.questions[: ctx.limit]
    mode = ctx.retrieval_mode or settings.RAG_RETRIEVAL_MODE
    saved_mode = settings.RAG_RETRIEVAL_MODE
    settings.RAG_RETRIEVAL_MODE = mode
    embedder = rag_module._get_embedder()
    rows = []
    try:
        with tempfile.TemporaryDirectory(prefix="intelliclaim-eval-") as directory:
            index, _, _ = _build_index(ctx, embedder, RAG_CHUNK_SIZE, directory)
            service = rag_module.RAGService(index_factory=lambda: index)
            async with groq_only() as recorder:
                for position, question in enumerate(questions, start=1):
                    try:
                        result = await with_retries(lambda q=question: service.query(q["question"], top_k=TOP_K))
                    except LLMError as exc:
                        rows.append({"id": question["id"], "error": exc.detail})
                        continue
                    rows.append(_score(question, result, NO_ANSWER))
                    if position % 20 == 0:
                        logger.info("rag-answer: %d/%d questions", position, len(questions))
        SharedSystemClient.clear_system_cache()
    finally:
        settings.RAG_RETRIEVAL_MODE = saved_mode

    by_id = {q["id"]: q for q in questions}
    answered = [row for row in rows if "error" not in row]
    answerable = [row for row in answered if by_id[row["id"]]["answerable"]]
    unanswerable = [row for row in answered if not by_id[row["id"]]["answerable"]]
    by_style: dict[str, list[bool]] = defaultdict(list)
    for row in answerable:
        by_style[by_id[row["id"]]["style"]].append(row["correct"])
    in_context = [row for row in answerable if row["source_retrieved"]]
    citing = [row for row in answerable if row["cited"]]
    metrics = {
        "answer_accuracy": _rate([row["correct"] for row in answerable]),
        "answer_accuracy_by_style": {style: _rate(values) for style, values in sorted(by_style.items())},
        "answer_accuracy_when_source_retrieved": _rate([row["correct"] for row in in_context]),
        "source_retrieved_rate": _rate([row["source_retrieved"] for row in answerable]),
        "citation_hit_rate": _rate([row["citation_hit"] for row in answerable]),
        "citation_precision": round(sum(row["citation_precision"] for row in citing) / len(citing), 4)
        if citing else 0.0,
        "answers_with_citations": _rate([bool(row["cited"]) for row in answerable]),
        "unanswerable_abstention_rate": _rate([row["abstained"] for row in unanswerable]),
        "unanswerable_cited_nothing_rate": _rate([not row["cited"] for row in unanswerable]),
        "questions": {"asked": len(questions), "answerable": len(answerable), "unanswerable": len(unanswerable),
                      "errors": len(rows) - len(answered)},
        "latency": latency_summary([call.seconds for call in recorder.calls]),
        "usage": usage_summary(recorder.calls, len(questions)),
    }
    return {
        "suite": NAME,
        "status": "ok",
        "config": {"model": settings.GROQ_MODEL, "retrieval_mode": mode, "top_k": TOP_K,
                   "chunk_size": RAG_CHUNK_SIZE},
        "metrics": metrics,
        "details": {"questions": rows},
    }


def _score(question: dict[str, Any], result: dict[str, Any], no_answer: str) -> dict[str, Any]:
    sources = set(question["source_document_ids"])
    cited = [c["doc_id"] for c in result["citations"]]
    answer = result["answer"]
    row: dict[str, Any] = {
        "id": question["id"],
        "answer": answer,
        "cited": cited,
        "source_retrieved": any(s["doc_id"] in sources for s in result["source_documents"]),
    }
    if question["answerable"]:
        row["correct"] = answer_matches(question["answer"], question["answer_type"], answer)
        row["citation_hit"] = bool(sources & set(cited))
        row["citation_precision"] = len(sources & set(cited)) / len(cited) if cited else 0.0
    else:
        row["abstained"] = compact(no_answer) in compact(answer)
    return row


def summary(result: dict[str, Any]) -> list[str]:
    m, c = result["metrics"], result["config"]
    counts, latency, usage = m["questions"], m["latency"], m["usage"]
    styles = ", ".join(f"{style} {value:.3f}" for style, value in m["answer_accuracy_by_style"].items())
    return [
        f"{counts['asked']} questions ({counts['answerable']} answerable, {counts['unanswerable']} unanswerable, "
        f"{counts['errors']} errors); Groq {c['model']}, {c['retrieval_mode']} retrieval, top_k={c['top_k']}, "
        f"{c['chunk_size']}-token chunks.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Answer accuracy | {m['answer_accuracy']:.3f} |",
        f"| Answer accuracy when a source chunk was retrieved | {m['answer_accuracy_when_source_retrieved']:.3f} |",
        f"| Source document retrieved (top 5) | {m['source_retrieved_rate']:.3f} |",
        f"| Citation hit rate (cites a source document) | {m['citation_hit_rate']:.3f} |",
        f"| Citation precision | {m['citation_precision']:.3f} |",
        f"| Answers with at least one citation | {m['answers_with_citations']:.3f} |",
        f"| Unanswerable: abstained | {m['unanswerable_abstention_rate']:.3f} |",
        f"| Unanswerable: cited nothing | {m['unanswerable_cited_nothing_rate']:.3f} |",
        "",
        f"Accuracy by question style: {styles}.",
        f"Latency p50 {latency.get('p50_ms')} ms, p95 {latency.get('p95_ms')} ms; "
        f"{usage['prompt_tokens_per_item']} prompt + {usage['completion_tokens_per_item']} completion tokens and "
        f"${usage['cost_usd_per_item']:.5f} per question.",
    ]
