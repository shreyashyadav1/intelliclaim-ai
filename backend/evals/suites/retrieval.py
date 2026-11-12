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
document type. answer-in-context@5 with neighbours repeats the check on what
the model is sent: the top 5 chunks plus their neighbouring chunks from the
same document (RAG_NEIGHBOR_CHUNKS), with the mean number of chunks sent.
Hybrid mode puts chunks that contain a document identifier named in the
question first (RAG_EXACT_IDENTIFIERS); "hybrid, fusion only" repeats the
default configuration without that step.
A grid over chunk sizes (128-512 tokens) and hybrid fusion
weights shows how sensitive the results are; config.py's defaults
(RAG_CHUNK_SIZE, HYBRID_WEIGHTS) and RAG_RETRIEVAL_MODE were chosen from it
(see evals/README.md).
"""

import logging
import tempfile
import time
from collections import defaultdict
from typing import Any

from config import (
    EMBEDDING_MODEL_NAME,
    HYBRID_CANDIDATES,
    HYBRID_WEIGHTS,
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RAG_EXACT_IDENTIFIERS,
    RAG_NEIGHBOR_CHUNKS,
    RRF_K,
)
from evals.common import Context
from evals.metrics import first_relevant_rank, latency_summary, normalize_whitespace, retrieval_metrics

NAME = "retrieval"
logger = logging.getLogger("evals.retrieval")

CHUNK_SIZES = (128, 256, 384, 512)
WEIGHT_VARIANTS = ((0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.2, 0.8), (0.1, 0.9))  # (vector, BM25)
FUSION_ONLY = "hybrid, fusion only"  # the default hybrid configuration without exact identifier matches
RANKED = 10  # chunks retrieved per question; MRR is computed over these
CONTEXT_K = 5  # the API's default top_k: chunks the model is sent before neighbours are added


def _label(weights: tuple[float, float]) -> str:
    return f"{weights[0]:g}/{weights[1]:g}"


def _answer_in(docs, question) -> bool:
    """A chunk of the question's source document contains the answer as printed."""
    from services.rag_chain import document_id

    surface = normalize_whitespace(question["answer_text"])
    return any(
        document_id(doc) in question["source_document_ids"] and surface in normalize_whitespace(doc.page_content)
        for doc in docs
    )


def _evaluate(
    index, questions, kinds, mode: str, weights: tuple[float, float], *, with_context: bool = False,
    exact_identifiers: bool = RAG_EXACT_IDENTIFIERS,
) -> dict[str, Any]:
    """Rank metrics over the top RANKED chunks (no neighbours); with_context also
    checks the context the API sends: the top CONTEXT_K chunks plus their neighbours."""
    from services.rag_chain import document_id

    ranks, hits, latencies, rows, context_hits, context_sizes = [], [], [], [], [], []
    by_style: dict[str, list] = defaultdict(list)
    by_kind: dict[str, list] = defaultdict(list)
    retriever = index.retriever(mode, RANKED, weights=weights, neighbors=0, exact_identifiers=exact_identifiers)
    context_retriever = (
        index.retriever(mode, CONTEXT_K, weights=weights, exact_identifiers=exact_identifiers)
        if with_context else None
    )
    for question in questions:
        started = time.perf_counter()
        docs = retriever.invoke(question["question"])
        latencies.append(time.perf_counter() - started)
        doc_ids = [document_id(doc) for doc in docs]
        rank = first_relevant_rank(doc_ids, question["source_document_ids"])
        hit = _answer_in(docs[:CONTEXT_K], question)
        ranks.append(rank)
        hits.append(hit)
        by_style[question["style"]].append(rank)
        by_kind[kinds[question["source_document_ids"][0]]].append(rank)
        row = {"id": question["id"], "rank": rank, "answer_in_top5": hit}
        if context_retriever is not None:
            context = context_retriever.invoke(question["question"])
            row["answer_in_context"] = _answer_in(context, question)
            row["context_chunks"] = len(context)
            context_hits.append(row["answer_in_context"])
            context_sizes.append(len(context))
        rows.append(row)

    metrics = retrieval_metrics(ranks)
    metrics["answer_in_context@5"] = round(sum(hits) / len(hits), 4)
    if context_hits:
        metrics["answer_in_context@5_with_neighbors"] = round(sum(context_hits) / len(context_hits), 4)
        metrics["context_chunks_mean"] = round(sum(context_sizes) / len(context_sizes), 3)
        metrics["neighbor_chunks"] = RAG_NEIGHBOR_CHUNKS
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
                main_config = chunk_size == RAG_CHUNK_SIZE and weights == default_weights
                result = _evaluate(index, questions, kinds, mode, weights, with_context=main_config)
                entry["configs"][_config_name(mode, weights)] = {
                    **result["metrics"], "by_style": result["by_style"],
                }
                if main_config:
                    main[mode] = result
                if main_config and mode == "hybrid":
                    fusion = _evaluate(index, questions, kinds, mode, weights, with_context=True,
                                       exact_identifiers=False)
                    entry["configs"][FUSION_ONLY] = {**fusion["metrics"], "by_style": fusion["by_style"]}
                    main[FUSION_ONLY] = fusion
            grid[str(chunk_size)] = entry
            del index
        SharedSystemClient.clear_system_cache()

    modes = ("vector", FUSION_ONLY, "hybrid")
    metrics = {
        "vector": main["vector"]["metrics"],
        "hybrid_fusion_only": main[FUSION_ONLY]["metrics"],
        "hybrid": main["hybrid"]["metrics"],
        "by_style": {mode: main[mode]["by_style"] for mode in modes},
        "by_source_type": {mode: main[mode]["by_kind"] for mode in modes},
        "latency": {mode: main[mode]["latency"] for mode in modes},
        "grid": grid,
    }
    rows = [
        {"id": v["id"], "vector_rank": v["rank"], "hybrid_rank": h["rank"],
         "vector_answer_in_top5": v["answer_in_top5"], "hybrid_answer_in_top5": h["answer_in_top5"],
         "vector_answer_in_context": v["answer_in_context"], "hybrid_answer_in_context": h["answer_in_context"],
         "vector_context_chunks": v["context_chunks"], "hybrid_context_chunks": h["context_chunks"],
         "fusion_only_rank": f["rank"], "fusion_only_answer_in_context": f["answer_in_context"]}
        for v, f, h in zip(main["vector"]["rows"], main[FUSION_ONLY]["rows"], main["hybrid"]["rows"], strict=True)
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
            "neighbor_chunks": RAG_NEIGHBOR_CHUNKS,
            "exact_identifiers": RAG_EXACT_IDENTIFIERS,
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
            f"| {m.get('answer_in_context@5', float('nan')):.3f} "
            f"| {m.get('answer_in_context@5_with_neighbors', float('nan')):.3f} "
            f"| {m.get('context_chunks_mean', float('nan')):.2f} |")


def summary(result: dict[str, Any]) -> list[str]:
    m, c = result["metrics"], result["config"]
    lines = [
        f"{c['questions']} answerable questions over {c['documents']} documents; embedding model "
        f"{c['embedding_model']}, chunks of {c['chunk_size']} tokens (overlap {c['chunk_overlap']}), "
        f"hybrid = vector + BM25 fused by weighted RRF (k={c['rrf_k']}, weights {c['hybrid_weights_vector_bm25']}).",
        "",
        "| Mode | Recall@1 | Recall@3 | Recall@5 | MRR@10 | Answer in top-5 | Answer in top-5 + neighbours "
        f"({c.get('neighbor_chunks', 0)} each side) | Chunks sent (mean) |",
        "|---|---|---|---|---|---|---|---|",
        _row("vector", m["vector"]),
        _row(FUSION_ONLY, m["hybrid_fusion_only"]),
        _row("hybrid", m["hybrid"]),
        "",
        "By question style (recall@1 / recall@5 / MRR):",
        "",
        "| Style | Vector | Hybrid, fusion only | Hybrid |",
        "|---|---|---|---|",
    ]
    modes = ("vector", FUSION_ONLY, "hybrid")

    def _cells(table: dict[str, Any], key: str) -> str:
        return " | ".join(
            f"{table[mode][key]['recall@1']:.3f} / {table[mode][key]['recall@5']:.3f} / {table[mode][key]['mrr']:.3f}"
            for mode in modes
        )

    for style in m["by_style"]["vector"]:
        lines.append(f"| {style} ({m['by_style']['vector'][style]['queries']}) | {_cells(m['by_style'], style)} |")
    lines += ["", "By source document type (recall@1 / recall@5 / MRR):", "",
              "| Source | Vector | Hybrid, fusion only | Hybrid |", "|---|---|---|---|"]
    for kind in m["by_source_type"]["vector"]:
        lines.append(f"| {kind} ({m['by_source_type']['vector'][kind]['queries']}) "
                     f"| {_cells(m['by_source_type'], kind)} |")
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
