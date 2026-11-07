"""
Retrieval suite (no API key needed).

Indexes the 60 text PDFs with the application's own pipeline (text layer
read by utils.pdf_parser, LlamaIndex chunking, fastembed embeddings,
ChromaDB) and asks every answerable question through the application's
LangChain retrievers. A question is a hit at k when a chunk of its source
document is among the first k chunks retrieved.

Reported per retrieval mode (vector, hybrid): recall@1/3/5, MRR (over the
top 10) and answer-in-context@5 (a top-5 chunk from the source document
contains the answer as printed), broken down by question style and source
document type. A grid over chunk sizes (128-512 tokens) and hybrid fusion
weights shows how sensitive the results are; config.py's defaults
(RAG_CHUNK_SIZE, HYBRID_WEIGHTS) and RAG_RETRIEVAL_MODE were chosen from it
(see evals/README.md).
"""

import logging
import tempfile
import time
from collections import defaultdict
from typing import Any

from config import EMBEDDING_MODEL_NAME, HYBRID_CANDIDATES, HYBRID_WEIGHTS, RAG_CHUNK_OVERLAP, RAG_CHUNK_SIZE, RRF_K
from evals.common import Context
from evals.metrics import first_relevant_rank, latency_summary, normalize_whitespace, retrieval_metrics

NAME = "retrieval"
logger = logging.getLogger("evals.retrieval")

CHUNK_SIZES = (128, 256, 384, 512)
WEIGHT_VARIANTS = ((0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.2, 0.8), (0.1, 0.9))  # (vector, BM25)
RANKED = 10  # chunks retrieved per question; MRR is computed over these


def _label(weights: tuple[float, float]) -> str:
    return f"{weights[0]:g}/{weights[1]:g}"


def _evaluate(index, questions, kinds, mode: str, weights: tuple[float, float]) -> dict[str, Any]:
    from services.rag_chain import document_id

    ranks, hits, latencies, rows = [], [], [], []
    by_style: dict[str, list] = defaultdict(list)
    by_kind: dict[str, list] = defaultdict(list)
    retriever = index.retriever(mode, RANKED, weights=weights)
    for question in questions:
        started = time.perf_counter()
        docs = retriever.invoke(question["question"])
        latencies.append(time.perf_counter() - started)
        doc_ids = [document_id(doc) for doc in docs]
        rank = first_relevant_rank(doc_ids, question["source_document_ids"])
        surface = normalize_whitespace(question["answer_text"])
        hit = any(
            doc_id in question["source_document_ids"] and surface in normalize_whitespace(doc.page_content)
            for doc_id, doc in zip(doc_ids[:5], docs[:5], strict=True)
        )
        ranks.append(rank)
        hits.append(hit)
        by_style[question["style"]].append(rank)
        by_kind[kinds[question["source_document_ids"][0]]].append(rank)
        rows.append({"id": question["id"], "rank": rank, "answer_in_top5": hit})

    metrics = retrieval_metrics(ranks)
    metrics["answer_in_context@5"] = round(sum(hits) / len(hits), 4)
    return {
        "metrics": metrics,
        "by_style": {style: retrieval_metrics(values) for style, values in sorted(by_style.items())},
        "by_kind": {kind: retrieval_metrics(values) for kind, values in sorted(by_kind.items())},
        "latency": latency_summary(latencies),
        "rows": rows,
    }


def _build_index(ctx: Context, embedder, chunk_size: int, directory: str):
    import chromadb

    from services.rag_index import COLLECTION_METADATA, VectorIndex

    client = chromadb.PersistentClient(path=directory)
    collection = client.create_collection("eval_docs", metadata=COLLECTION_METADATA)
    index = VectorIndex(client, collection, lambda: embedder, chunk_size=chunk_size,
                        chunk_overlap=RAG_CHUNK_OVERLAP * chunk_size // RAG_CHUNK_SIZE)
    started = time.perf_counter()
    chunks = 0
    for doc in ctx.documents:
        paged = ctx.text_layer[doc["id"]]
        metadata = {"filename": doc["filename"], "document_class": doc["document_class"]}
        chunks += index.add_document(doc["id"], paged.text, metadata, paged.page_starts)
    return index, chunks, time.perf_counter() - started


def _config_name(mode: str, weights: tuple[float, float]) -> str:
    return "vector" if mode == "vector" else f"hybrid {_label(weights)}"


def run(ctx: Context) -> dict[str, Any]:
    from chromadb.api.shared_system_client import SharedSystemClient

    from services import rag_service

    embedder = rag_service._get_embedder()  # the production model, cached under FASTEMBED_CACHE_PATH
    questions = [q for q in ctx.questions if q["answerable"]]
    kinds = {doc["id"]: doc["kind"] for doc in ctx.documents}
    default_weights = tuple(HYBRID_WEIGHTS)
    configs = [("vector", default_weights)] + [("hybrid", weights) for weights in WEIGHT_VARIANTS]
    if ("hybrid", default_weights) not in configs:
        configs.append(("hybrid", default_weights))

    grid: dict[str, Any] = {}
    main: dict[str, Any] = {}
    for chunk_size in CHUNK_SIZES:
        with tempfile.TemporaryDirectory(prefix="intelliclaim-eval-") as directory:
            index, chunks, seconds = _build_index(ctx, embedder, chunk_size, directory)
            logger.info("chunk size %d: %d chunks indexed in %.1fs", chunk_size, chunks, seconds)
            entry: dict[str, Any] = {"chunks": chunks, "index_seconds": round(seconds, 2), "configs": {}}
            for mode, weights in configs:
                result = _evaluate(index, questions, kinds, mode, weights)
                entry["configs"][_config_name(mode, weights)] = {
                    **result["metrics"], "by_style": result["by_style"],
                }
                if chunk_size == RAG_CHUNK_SIZE and weights == default_weights:
                    main[mode] = result
            grid[str(chunk_size)] = entry
            del index
        SharedSystemClient.clear_system_cache()

    metrics = {
        "vector": main["vector"]["metrics"],
        "hybrid": main["hybrid"]["metrics"],
        "by_style": {mode: main[mode]["by_style"] for mode in ("vector", "hybrid")},
        "by_source_type": {mode: main[mode]["by_kind"] for mode in ("vector", "hybrid")},
        "latency": {mode: main[mode]["latency"] for mode in ("vector", "hybrid")},
        "grid": grid,
    }
    rows = [
        {"id": v["id"], "vector_rank": v["rank"], "hybrid_rank": h["rank"],
         "vector_answer_in_top5": v["answer_in_top5"], "hybrid_answer_in_top5": h["answer_in_top5"]}
        for v, h in zip(main["vector"]["rows"], main["hybrid"]["rows"], strict=True)
    ]
    return {
        "suite": NAME,
        "status": "ok",
        "config": {
            "embedding_model": EMBEDDING_MODEL_NAME,
            "chunk_size": RAG_CHUNK_SIZE,
            "chunk_overlap": RAG_CHUNK_OVERLAP,
            "hybrid_weights_vector_bm25": list(HYBRID_WEIGHTS),
            "rrf_k": RRF_K,
            "hybrid_candidates": HYBRID_CANDIDATES,
            "documents": len(ctx.documents),
            "questions": len(questions),
            "ranked_per_question": RANKED,
        },
        "metrics": metrics,
        "details": {"questions": rows},
    }


def _row(name: str, m: dict[str, Any]) -> str:
    return (f"| {name} | {m['recall@1']:.3f} | {m['recall@3']:.3f} | {m['recall@5']:.3f} | {m['mrr']:.3f} "
            f"| {m.get('answer_in_context@5', float('nan')):.3f} |")


def summary(result: dict[str, Any]) -> list[str]:
    m, c = result["metrics"], result["config"]
    lines = [
        f"{c['questions']} answerable questions over {c['documents']} documents; embedding model "
        f"{c['embedding_model']}, chunks of {c['chunk_size']} tokens (overlap {c['chunk_overlap']}), "
        f"hybrid = vector + BM25 fused by weighted RRF (k={c['rrf_k']}, weights {c['hybrid_weights_vector_bm25']}).",
        "",
        "| Mode | Recall@1 | Recall@3 | Recall@5 | MRR@10 | Answer in top-5 |",
        "|---|---|---|---|---|---|",
        _row("vector", m["vector"]),
        _row("hybrid", m["hybrid"]),
        "",
        "By question style (recall@1 / recall@5 / MRR):",
        "",
        "| Style | Vector | Hybrid |",
        "|---|---|---|",
    ]
    for style in m["by_style"]["vector"]:
        v, h = m["by_style"]["vector"][style], m["by_style"]["hybrid"][style]
        lines.append(f"| {style} ({v['queries']}) | {v['recall@1']:.3f} / {v['recall@5']:.3f} / {v['mrr']:.3f} "
                     f"| {h['recall@1']:.3f} / {h['recall@5']:.3f} / {h['mrr']:.3f} |")
    lines += ["", "By source document type (recall@1 / recall@5 / MRR):", "", "| Source | Vector | Hybrid |",
              "|---|---|---|"]
    for kind in m["by_source_type"]["vector"]:
        v, h = m["by_source_type"]["vector"][kind], m["by_source_type"]["hybrid"][kind]
        lines.append(f"| {kind} ({v['queries']}) | {v['recall@1']:.3f} / {v['recall@5']:.3f} / {v['mrr']:.3f} "
                     f"| {h['recall@1']:.3f} / {h['recall@5']:.3f} / {h['mrr']:.3f} |")
    styles = list(m["by_style"]["vector"])
    lines += [
        "",
        "Grid over chunk size and fusion weights (vector/BM25): recall@1 / recall@5 / MRR / answer-in-top-5 for "
        "all questions, then recall@5 / MRR per question style.",
        "",
        "| Chunk size (chunks) | Configuration | All questions | " + " | ".join(styles) + " |",
        "|---|---|---|" + "---|" * len(styles),
    ]
    for size, entry in m["grid"].items():
        for name, cell in entry["configs"].items():
            per_style = " | ".join(
                f"{cell['by_style'][style]['recall@5']:.3f} / {cell['by_style'][style]['mrr']:.3f}" for style in styles
            )
            lines.append(
                f"| {size} ({entry['chunks']}) | {name} | {cell['recall@1']:.3f} / {cell['recall@5']:.3f} / "
                f"{cell['mrr']:.3f} / {cell['answer_in_context@5']:.3f} | {per_style} |"
            )
    vector, hybrid = m["latency"]["vector"], m["latency"]["hybrid"]
    lines += ["", f"Retrieval latency per question (p50/p95): vector {vector['p50_ms']}/{vector['p95_ms']} ms, "
              f"hybrid {hybrid['p50_ms']}/{hybrid['p95_ms']} ms."]
    return lines
