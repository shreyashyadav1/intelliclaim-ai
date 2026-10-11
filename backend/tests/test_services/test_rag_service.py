"""Tests for the RAG service internals: embeddings, vector lifecycle and the OpenAI path."""

import fastembed
import pytest
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import services.rag_service as rag_module
from config import EMBEDDING_MODEL_NAME, settings
from services.rag_service import rag_service

LONG_TEXT = " ".join(f"Line {i}: itemised charge for appendicitis treatment." for i in range(60))


def _vector_count(doc_id: str) -> int:
    return len(rag_module._require_collection().get(where={"doc_id": doc_id}, include=[])["ids"])


# --- fastembed singleton -------------------------------------------------------------


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


# --- Vector lifecycle ------------------------------------------------------------------


async def test_reindexing_replaces_old_chunks():
    first = await rag_service.index_document("doc-a", LONG_TEXT, {"filename": "a.pdf"})
    assert first > 1
    assert await rag_service.index_document("doc-a", "Short replacement text.", {"filename": "a.pdf"}) == 1
    assert _vector_count("doc-a") == 1


async def test_delete_document_removes_only_its_vectors():
    await rag_service.index_document("doc-a", LONG_TEXT, {"filename": "a.pdf"})
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


# --- OpenAI path passes the key explicitly (it may only exist in backend/.env) ----------


class _FakeLangChainEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return rag_module._embed(texts)

    def embed_query(self, text):
        return rag_module._embed([text])[0]


async def test_langchain_query_passes_the_openai_key_explicitly(monkeypatch):
    import langchain_openai

    recorded = {}

    def _embeddings(**kwargs):
        recorded["embeddings"] = kwargs
        return _FakeLangChainEmbeddings()

    def _chat(**kwargs):
        recorded["chat"] = kwargs
        return FakeListChatModel(responses=["Answer from the chain."])

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-only-in-dotenv")
    monkeypatch.setattr(langchain_openai, "OpenAIEmbeddings", _embeddings)
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _chat)
    metadata = {"doc_id": "doc-a", "filename": "a.pdf"}
    rag_service._index_with_fastembed("doc-a", "Appendicitis surgery invoice.", metadata)

    result = await rag_service.query("appendicitis invoice", top_k=1)

    assert result["answer"] == "Answer from the chain."
    assert result["source"] == "openai"
    assert result["source_documents"][0]["doc_id"] == "doc-a"
    assert recorded["embeddings"]["api_key"] == "sk-only-in-dotenv"
    assert recorded["chat"]["api_key"] == "sk-only-in-dotenv"
    assert recorded["chat"]["model"] == settings.OPENAI_MODEL


async def test_langchain_failure_falls_back_to_groq(monkeypatch, fake_groq):
    import langchain_openai

    def _broken(**kwargs):
        raise RuntimeError("openai down")

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(langchain_openai, "OpenAIEmbeddings", _broken)
    rag_service._index_with_fastembed("doc-a", "Appendicitis surgery invoice.", {"doc_id": "doc-a"})
    fake_groq.respond("Groq answer.")

    result = await rag_service.query("appendicitis")

    assert result["source"] == "groq"
    assert result["answer"] == "Groq answer."


async def test_llamaindex_indexing_passes_the_key_and_tags_chunks_with_our_doc_id(monkeypatch):
    """LlamaIndex used to write its own random UUID into doc_id, so deletes found nothing."""
    import llama_index.embeddings.openai as llama_openai
    from llama_index.core.embeddings import MockEmbedding

    recorded = {}

    def _embedding(**kwargs):
        recorded.update(kwargs)
        return MockEmbedding(embed_dim=16)

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-only-in-dotenv")
    monkeypatch.setattr(llama_openai, "OpenAIEmbedding", _embedding)
    text = LONG_TEXT * 20

    chunks = await rag_service.index_document("doc-li", text, {"filename": "li.pdf", "claim_id": None})
    assert chunks >= 1
    assert recorded["api_key"] == "sk-only-in-dotenv"
    assert _vector_count("doc-li") == chunks

    assert await rag_service.index_document("doc-li", text, {"filename": "li.pdf"}) == chunks  # no duplicates
    assert await rag_service.delete_document("doc-li") == chunks
    assert _vector_count("doc-li") == 0


@pytest.mark.parametrize("mock", [True, False])
async def test_query_modes_never_return_canned_sources(monkeypatch, mock):
    monkeypatch.setattr(settings, "MOCK_LLM", mock)
    if mock:
        result = await rag_service.query("anything")
        assert result["source_documents"] == []
    else:
        with pytest.raises(rag_module.LLMNotConfiguredError):
            await rag_service.query("anything")
