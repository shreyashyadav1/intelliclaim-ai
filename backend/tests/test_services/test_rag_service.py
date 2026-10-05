"""Tests for the RAG pipeline: LlamaIndex ingestion, LangChain retrieval, hybrid fusion and the LCEL chain.

Embeddings come from the conftest FakeEmbedder (or small stubs defined here);
chat models are LangChain fakes or FakeGroq, so no test calls a provider.
"""

import asyncio
import os
import tempfile

import fastembed
import numpy as np
import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.retrievers import BaseRetriever

import services.rag_service as rag_module
from config import EMBEDDING_MODEL_NAME, RAG_ANSWER_PARAMS, settings
from services import llm, rag_chain
from services.rag_index import (
    KeywordRetriever,
    SharedFastEmbedEmbedding,
    VectorIndex,
    hybrid_retriever,
    keyword_tokens,
    langchain_embeddings,
    page_documents,
)
from services.rag_service import rag_service

LONG_TEXT = " ".join(f"Line {i}: itemised charge for appendicitis treatment." for i in range(60))


def _vector_count(doc_id: str) -> int:
    return len(rag_module._require_collection().get(where={"doc_id": doc_id}, include=[])["ids"])


def _index() -> VectorIndex:
    return rag_service._vector_index()


# --- One fastembed model for both frameworks ----------------------------------------------


def test_embedder_loads_the_explicit_model_once_from_the_cache_path(isolated_vector_store, monkeypatch):
    created = []

    class _RecordingTextEmbedding:
        def __init__(self, model_name, cache_dir=None, **kwargs):
            created.append((model_name, cache_dir))

    monkeypatch.setattr(fastembed, "TextEmbedding", _RecordingTextEmbedding)
    monkeypatch.setattr(settings, "FASTEMBED_CACHE_PATH", "/opt/fastembed-cache")
    get_embedder = isolated_vector_store.get_embedder

    first, second = get_embedder(), get_embedder()

    assert first is second
    assert created == [(EMBEDDING_MODEL_NAME, "/opt/fastembed-cache")]
    assert EMBEDDING_MODEL_NAME == "BAAI/bge-small-en-v1.5"


def test_blank_cache_path_uses_fastembeds_default_directory(isolated_vector_store, monkeypatch):
    """A blank FASTEMBED_CACHE_PATH (as copied from .env.example) must not mean the working directory."""
    created = []

    class _RecordingTextEmbedding:
        def __init__(self, model_name, cache_dir=None, **kwargs):
            created.append(cache_dir)

    monkeypatch.setattr(fastembed, "TextEmbedding", _RecordingTextEmbedding)
    monkeypatch.setattr(settings, "FASTEMBED_CACHE_PATH", None)  # the setting maps blank to None
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", "")  # fastembed would read this as "."

    isolated_vector_store.get_embedder()

    assert created == [os.path.join(tempfile.gettempdir(), "fastembed_cache")]


def test_llamaindex_and_langchain_embed_with_the_same_model_instance(monkeypatch):
    def _no_second_model(*args, **kwargs):
        raise AssertionError("a second fastembed model was loaded")

    monkeypatch.setattr(fastembed, "TextEmbedding", _no_second_model)
    model = rag_module._get_embedder()

    llama = SharedFastEmbedEmbedding(model)
    lang = langchain_embeddings(model)

    question = "What was the appendicitis treatment cost?"
    assert np.allclose(llama.get_query_embedding(question), lang.embed_query(question))
    assert np.allclose(llama.get_text_embedding_batch(["a b", "c"]), lang.embed_documents(["a b", "c"]))
    assert lang.model is model


def test_counting_and_deleting_do_not_load_the_embedding_model(monkeypatch):
    def _factory():
        raise AssertionError("the embedding model was loaded")

    index = VectorIndex(rag_module._get_chroma_client(), rag_module._require_collection(), _factory)
    assert index.count() == 0
    assert index.delete_document("doc-a") == 0


# --- Ingestion (LlamaIndex) ------------------------------------------------------------------


def test_page_documents_tag_pages_and_keep_metadata_out_of_the_embedded_text():
    text = "Invoice INV-1001.\n\nTotal due $10.00."
    docs = page_documents("doc-a", text, {"filename": "a.pdf", "doc_id": "spoofed", "claim_id": None}, [0, 19])

    assert [doc.metadata for doc in docs] == [{"filename": "a.pdf", "page": 1}, {"filename": "a.pdf", "page": 2}]
    assert all(doc.id_ == "doc-a" for doc in docs)
    assert docs[1].get_content(metadata_mode="embed") == "Total due $10.00."


async def test_long_documents_are_split_by_the_sentence_splitter():
    chunks = await rag_service.index_document("doc-a", LONG_TEXT * 4, {"filename": "a.pdf"}, [0])
    assert chunks > 1

    stored = rag_module._require_collection().get(where={"doc_id": "doc-a"}, include=["documents", "metadatas"])
    assert sorted(stored["ids"]) == sorted(f"doc-a:p1:{i}" for i in range(chunks))
    assert all(meta["page"] == 1 and meta["document_id"] == "doc-a" for meta in stored["metadatas"])
    assert all(len(text) < len(LONG_TEXT * 4) for text in stored["documents"])


async def test_reindexing_replaces_old_chunks():
    first = await rag_service.index_document("doc-a", LONG_TEXT * 4, {"filename": "a.pdf"})
    assert first > 1
    assert await rag_service.index_document("doc-a", "Short replacement text.", {"filename": "a.pdf"}) == 1
    assert _vector_count("doc-a") == 1


async def test_a_failed_embedding_keeps_the_previous_vectors(monkeypatch):
    await rag_service.index_document("doc-a", "Appendicitis invoice.", {"filename": "a.pdf"})

    class _Broken:
        def embed(self, texts, **kwargs):
            raise RuntimeError("model crashed")

    monkeypatch.setattr(rag_module, "_get_embedder", _Broken)
    with pytest.raises(RuntimeError):
        await rag_service.index_document("doc-a", "New text.", {"filename": "a.pdf"})
    assert _vector_count("doc-a") == 1


async def test_delete_document_removes_only_its_vectors():
    await rag_service.index_document("doc-a", LONG_TEXT * 4, {"filename": "a.pdf"})
    await rag_service.index_document("doc-b", "Another document.", {"filename": "b.pdf"})

    removed = await rag_service.delete_document("doc-a")

    assert removed > 1
    assert _vector_count("doc-a") == 0
    assert _vector_count("doc-b") == 1
    assert await rag_service.delete_document("doc-a") == 0


async def test_none_metadata_values_are_dropped():
    await rag_service.index_document("doc-a", "Some text.", {"filename": "a.pdf", "claim_id": None})
    metadata = rag_module._require_collection().get(where={"doc_id": "doc-a"})["metadatas"][0]
    assert "claim_id" not in metadata


async def test_empty_text_is_not_indexed():
    assert await rag_service.index_document("doc-a", "   ", {}) == 0


async def test_chunks_from_the_previous_fastembed_path_stay_searchable_and_deletable(mock_llm):
    """Before LlamaIndex ingestion, chunks were written directly with a doc_id and chunk_index."""
    embedding = next(rag_module._get_embedder().embed(["Appendicitis surgery invoice."])).tolist()
    rag_module._require_collection().upsert(
        ids=["doc-old_chunk_0"],
        embeddings=[embedding],
        documents=["Appendicitis surgery invoice."],
        metadatas=[{"doc_id": "doc-old", "filename": "old.pdf", "chunk_index": 0}],
    )

    result = await rag_service.query("appendicitis surgery")

    assert result["source_documents"][0]["doc_id"] == "doc-old"
    assert result["citations"] == [{"doc_id": "doc-old", "filename": "old.pdf", "pages": []}]
    assert await rag_service.delete_document("doc-old") == 1


# --- Retrieval (LangChain) ----------------------------------------------------------------------


def test_keyword_tokens_keep_identifiers_and_their_parts():
    assert keyword_tokens("Total for Invoice INV-1043: $4,512.30!") == [
        "total", "for", "invoice", "inv-1043", "inv", "1043", "4", "512.30", "512", "30",
    ]


async def test_vector_retriever_scores_are_cosine_similarities():
    await rag_service.index_document("doc-a", "Appendicitis surgery invoice.", {"filename": "a.pdf"})
    await rag_service.index_document("doc-b", "Diabetes follow-up visit.", {"filename": "b.pdf"})

    docs = _index().retriever("vector", 2).invoke("appendicitis surgery invoice")

    assert [doc.metadata["document_id"] for doc in docs] == ["doc-a", "doc-b"]
    assert docs[0].metadata["score"] == pytest.approx(1.0, abs=1e-6)
    assert 0.0 <= docs[1].metadata["score"] < docs[0].metadata["score"]
    assert all("_node_content" not in doc.metadata for doc in docs)


def test_keyword_retriever_drops_chunks_without_a_matching_term():
    corpus = [
        Document(page_content="Invoice INV-1043 total $10.", id="c1"),
        Document(page_content="Discharge summary DS-2001.", id="c2"),
    ]
    retriever = KeywordRetriever.from_documents(corpus, preprocess_func=keyword_tokens, k=5)

    assert [doc.metadata["chunk_id"] for doc in retriever.invoke("INV-1043")] == ["c1"]
    assert retriever.invoke("pneumonia") == []


class _Fixed(BaseRetriever):
    """Returns a fixed ranked list of chunk ids."""

    ranking: list[str]
    scores: dict[str, float] = {}

    def _get_relevant_documents(self, query, *, run_manager):
        docs = []
        for chunk_id in self.ranking:
            metadata = {"chunk_id": chunk_id}
            if chunk_id in self.scores:
                metadata["score"] = self.scores[chunk_id]
            docs.append(Document(page_content=f"text of {chunk_id}", metadata=metadata, id=chunk_id))
        return docs


def test_hybrid_fusion_ranks_by_weighted_reciprocal_rank():
    vector = _Fixed(ranking=["a", "b", "c"], scores={"a": 0.9, "b": 0.8, "c": 0.7})
    keyword = _Fixed(ranking=["c", "d", "a"])
    filled = []

    def _fill(query, docs):
        for doc in docs:
            if "score" not in doc.metadata:
                filled.append(doc.metadata["chunk_id"])
                doc.metadata["score"] = 0.5

    docs = hybrid_retriever(vector, keyword, k=3, fill_scores=_fill).invoke("q")

    # a: 1/61 + 1/63, c: 1/63 + 1/61 (tie, vector order breaks it), b: 1/62, d: 1/62
    assert [doc.metadata["chunk_id"] for doc in docs] == ["a", "c", "b"]
    assert [doc.metadata["score"] for doc in docs] == [0.9, 0.7, 0.8]  # vector copies keep their score
    assert filled == []


def test_hybrid_weights_and_score_backfill():
    vector = _Fixed(ranking=["a", "b"], scores={"a": 0.9, "b": 0.8})
    keyword = _Fixed(ranking=["z", "b"])

    def _fill(query, docs):
        for doc in docs:
            doc.metadata.setdefault("score", 0.1)

    docs = hybrid_retriever(vector, keyword, k=2, weights=(0.2, 0.8), fill_scores=_fill).invoke("q")

    assert [doc.metadata["chunk_id"] for doc in docs] == ["b", "z"]
    assert docs[1].metadata["score"] == 0.1


class _TopicEmbedder:
    """Embeds by topic word counts, so identifiers such as invoice numbers are invisible to it."""

    TOPICS = ("invoice", "discharge", "policy")

    def embed(self, texts, **kwargs):
        for text in [texts] if isinstance(texts, str) else texts:
            lowered = text.lower()
            vector = np.array([1.0 + lowered.count(topic) for topic in self.TOPICS])
            yield vector / np.linalg.norm(vector)

    def query_embed(self, query, **kwargs):
        yield from self.embed(query)


async def test_hybrid_retrieval_promotes_identifier_matches_that_embeddings_miss(monkeypatch):
    monkeypatch.setattr(rag_module, "_get_embedder", _TopicEmbedder)
    await rag_service.index_document("target", "Remittance advice for INV-1004.", {})
    for number in range(4):
        await rag_service.index_document(f"other-{number}", "Invoice invoice: total due.", {})
    question = "invoice INV-1004 total"

    def _rank(mode: str, **kwargs) -> int:
        docs = _index().retriever(mode, 5, **kwargs).invoke(question)
        return [doc.metadata["document_id"] for doc in docs].index("target") + 1

    assert _rank("vector") == 5  # the embedder prefers every other invoice
    assert _rank("hybrid") < _rank("vector")  # BM25's exact identifier match moves it up
    assert _rank("hybrid", weights=(0.2, 0.8)) == 1
    hybrid = _index().retriever("hybrid", 5).invoke(question)
    assert all(0.0 <= doc.metadata["score"] <= 1.0 for doc in hybrid)  # BM25-only hits get a similarity too


async def test_bm25_corpus_follows_index_changes():
    index = _index()
    await asyncio.to_thread(index.add_document, "doc-a", "Invoice INV-1001.", {})
    assert [d.metadata["document_id"] for d in index.retriever("hybrid", 5).invoke("INV-1001")] == ["doc-a"]

    await asyncio.to_thread(index.delete_document, "doc-a")
    await asyncio.to_thread(index.add_document, "doc-b", "Invoice INV-2002.", {})

    assert [d.metadata["document_id"] for d in index.retriever("hybrid", 5).invoke("INV-2002")] == ["doc-b"]
    assert all(d.metadata["document_id"] != "doc-a" for d in index.retriever("hybrid", 5).invoke("INV-1001"))


def test_unknown_retrieval_mode_is_rejected():
    with pytest.raises(ValueError):
        _index().retriever("fuzzy", 5)


def test_retrieval_mode_setting_is_validated(monkeypatch):
    from config import Settings

    monkeypatch.setenv("RAG_RETRIEVAL_MODE", " Hybrid ")
    assert Settings(_env_file=None).RAG_RETRIEVAL_MODE == "hybrid"
    monkeypatch.setenv("RAG_RETRIEVAL_MODE", "keyword")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


# --- The LCEL chain -------------------------------------------------------------------------


def _docs() -> list[Document]:
    return [
        Document(page_content="Invoice INV-1043. Total due: $4,512.30.",
                 metadata={"document_id": "doc-inv", "filename": "inv.pdf", "page": 1}),
        Document(page_content="Discharge summary for Olivia Park.",
                 metadata={"document_id": "doc-ds", "filename": "ds.pdf", "page": 2}),
    ]


class _StaticRetriever(BaseRetriever):
    docs: list[Document]

    def _get_relevant_documents(self, query, *, run_manager):
        return self.docs


class _RecordingChat(FakeListChatModel):
    prompts: list = []

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        self.prompts.append(messages)
        return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)


async def test_chain_answers_from_numbered_context():
    chat = _RecordingChat(responses=["The total due is $4,512.30 [1]."], prompts=[])
    chain = rag_chain.build_rag_chain(_StaticRetriever(docs=_docs()), rag_chain.build_answer_chain(chat, "groq"))

    output = await chain.ainvoke("What is the total on INV-1043?")

    assert output["answer"] == {"text": "The total due is $4,512.30 [1].", "provider": "groq"}
    assert output["question"] == "What is the total on INV-1043?"
    system, human = chat.prompts[0]
    assert "ONLY the numbered context excerpts" in system.content
    assert "[1] inv.pdf, page 1\nInvoice INV-1043." in human.content
    assert "[2] ds.pdf, page 2" in human.content
    assert human.content.endswith("Question: What is the total on INV-1043?")


async def test_chain_skips_the_model_when_nothing_is_retrieved():
    chat = _RecordingChat(responses=["should not be used"], prompts=[])
    chain = rag_chain.build_rag_chain(_StaticRetriever(docs=[]), rag_chain.build_answer_chain(chat, "groq"))

    output = await chain.ainvoke("anything")

    assert output["answer"] == {"text": rag_chain.NO_MATCH_ANSWER, "provider": None}
    assert chat.prompts == []


async def test_blank_model_output_is_an_output_error():
    chain = rag_chain.build_answer_chain(FakeListChatModel(responses=["  "]), "groq")
    with pytest.raises(llm.LLMOutputError):
        await chain.ainvoke({"question": "q", "docs": _docs()})


async def test_provider_fallbacks_move_to_the_next_chat_model(fake_groq, groq_errors):
    fake_groq.respond(groq_errors.connection())
    failing = rag_chain.build_answer_chain(llm.chat_model("groq", RAG_ANSWER_PARAMS), "groq")
    backup = rag_chain.build_answer_chain(FakeListChatModel(responses=["Backup answer [2]."]), "openai")

    answer = await rag_chain.with_provider_fallbacks([failing, backup]).ainvoke({"question": "q", "docs": _docs()})

    assert answer == {"text": "Backup answer [2].", "provider": "openai"}


def test_mock_answer_quotes_and_cites_the_closest_excerpt():
    answer = rag_chain.mock_answer_chain().invoke({"question": "q", "docs": _docs()})
    assert answer["text"].startswith(rag_chain.MOCK_PREFIX)
    assert "Invoice INV-1043" in answer["text"]
    assert rag_chain.citations(answer["text"], _docs())[0]["doc_id"] == "doc-inv"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Total is $4,512.30 [1].", ["doc-inv"]),
        ("Both [2][1].", ["doc-ds", "doc-inv"]),
        ("Both [1, 2] again [1].", ["doc-inv", "doc-ds"]),
        ("Out of range [3] and [0].", []),
        (rag_chain.NO_ANSWER, []),
    ],
)
def test_citations_map_excerpt_numbers_to_documents(answer, expected):
    assert [c["doc_id"] for c in rag_chain.citations(answer, _docs())] == expected


def test_citations_list_each_document_once_with_its_pages():
    docs = [*_docs(), Document(page_content="More.", metadata={"document_id": "doc-inv", "filename": "inv.pdf",
                                                                "page": 3})]
    assert rag_chain.citations("[3] and [1]", docs) == [{"doc_id": "doc-inv", "filename": "inv.pdf", "pages": [1, 3]}]


# --- Chat models over the shared SDK clients ------------------------------------------------


async def test_chat_groq_uses_the_configured_model_and_the_shared_client(fake_groq):
    fake_groq.respond("Hello.")
    model = llm.chat_model("groq", RAG_ANSWER_PARAMS)

    reply = await model.ainvoke("Hi")

    assert reply.content == "Hello."
    call = fake_groq.calls[0]
    assert call["model"] == settings.GROQ_MODEL
    assert call["temperature"] == RAG_ANSWER_PARAMS.temperature
    assert call["max_tokens"] == RAG_ANSWER_PARAMS.max_tokens
    with pytest.raises(RuntimeError, match="async calls only"):
        model.invoke("Hi")


async def test_chat_groq_answers_with_the_content_of_a_reasoning_model(fake_groq):
    fake_groq.respond_with_reasoning("The total is $4,512.30 [1].", reasoning="Excerpt 1 states the total.")
    reply = await llm.chat_model("groq", RAG_ANSWER_PARAMS).ainvoke("What is the total?")

    assert reply.content == "The total is $4,512.30 [1]."
    assert RAG_ANSWER_PARAMS.max_tokens >= 1024  # gpt-oss reasoning counts toward the limit


def test_chat_model_requires_a_configured_provider():
    with pytest.raises(llm.LLMNotConfiguredError):
        llm.chat_model("groq", RAG_ANSWER_PARAMS)
    with pytest.raises(ValueError):
        llm.chat_model("other", RAG_ANSWER_PARAMS)


@pytest.mark.parametrize("mock", [True, False])
async def test_query_modes_never_return_canned_sources(monkeypatch, mock):
    monkeypatch.setattr(settings, "MOCK_LLM", mock)
    if mock:
        result = await rag_service.query("anything")
        assert result["source_documents"] == []
    else:
        with pytest.raises(rag_module.LLMNotConfiguredError):
            await rag_service.query("anything")
