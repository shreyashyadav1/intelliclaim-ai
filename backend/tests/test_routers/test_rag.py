"""
IntelliClaim AI - RAG Router Tests

Retrieval runs against a per-test ChromaDB with the fake embedder; answers
come from FakeGroq (through LangChain's ChatGroq) or MOCK_LLM, never from a
real provider.
"""

import pytest

import services.rag_service as rag_module
from config import settings
from services import llm


async def _index(async_client, doc_id: str) -> dict:
    response = await async_client.post(f"/api/rag/index/{doc_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _stored_chunks() -> list[dict]:
    return rag_module._require_collection().get(include=["metadatas"])["metadatas"]


def _add_legacy_vectors(dimension: int) -> None:
    """Vectors as the old OpenAI path stored them (1536-dimensional text-embedding-3-small)."""
    rag_module._require_collection().add(
        ids=["legacy_chunk_0"],
        embeddings=[[0.01] * dimension],
        documents=["Legacy chunk embedded by another model."],
        metadatas=[{"doc_id": "doc-legacy", "filename": "old.pdf"}],
    )


# --- Indexing ------------------------------------------------------------------------


async def test_index_document_stores_chunks(async_client):
    data = await _index(async_client, "doc-test-001")
    assert data == {"success": True, "document_id": "doc-test-001", "chunks_indexed": 1}

    stats = (await async_client.get("/api/rag/stats")).json()
    assert stats == {
        "indexed_chunks": 1,
        "status": "ready",
        "retrieval_mode": settings.RAG_RETRIEVAL_MODE,
        "embedding_model": "BAAI/bge-small-en-v1.5",
    }


async def test_chunks_carry_document_metadata(async_client, test_db):
    await test_db.documents.update_one({"_id": "doc-test-001"}, {"$set": {"page_count": 1}})
    await _index(async_client, "doc-test-001")

    (metadata,) = _stored_chunks()
    assert metadata["document_id"] == "doc-test-001"
    assert metadata["doc_id"] == "doc-test-001"  # older chunks are deleted by this key
    assert metadata["filename"] == "invoice_test.pdf"
    assert metadata["document_class"] == "invoice"
    assert metadata["page"] == 1


async def test_multi_page_documents_are_indexed_page_by_page(async_client, test_db):
    pages = ["Invoice INV-2001 for Olivia Park.", "Total amount due: $4,512.30."]
    text = "\n\n".join(pages)
    await test_db.documents.update_one(
        {"_id": "doc-test-001"},
        {"$set": {"extracted_text": text, "page_starts": [0, len(pages[0]) + 2], "page_count": 2}},
    )

    assert (await _index(async_client, "doc-test-001"))["chunks_indexed"] == 2
    assert sorted(meta["page"] for meta in _stored_chunks()) == [1, 2]


async def test_index_document_not_found(async_client):
    assert (await async_client.post("/api/rag/index/nonexistent")).status_code == 404


async def test_index_document_without_text_is_400(async_client, test_db):
    await test_db.documents.update_one({"_id": "doc-test-001"}, {"$set": {"extracted_text": None}})
    assert (await async_client.post("/api/rag/index/doc-test-001")).status_code == 400


async def test_index_failure_is_a_generic_500(async_client, monkeypatch):
    class _BrokenEmbedder:
        def embed(self, texts, **kwargs):
            raise RuntimeError("onnxruntime: secret internal path /opt/model")

    monkeypatch.setattr(rag_module, "_get_embedder", _BrokenEmbedder)
    response = await async_client.post("/api/rag/index/doc-test-001")
    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to index the document"}


async def test_index_all_rebuilds_the_index(async_client, test_db):
    await test_db.documents.insert_one({
        "_id": "doc-failed", "processing_status": "failed", "extracted_text": "", "error_message": "No text",
    })
    _add_legacy_vectors(8)  # stale vectors of any shape are cleared by the rebuild

    data = (await async_client.post("/api/rag/index-all")).json()

    assert data == {"indexed": 2, "errors": 0, "total": 2, "chunks_indexed": 2}
    assert sorted(meta["document_id"] for meta in _stored_chunks()) == ["doc-test-001", "doc-test-002"]


async def test_index_all_reports_failures(async_client, monkeypatch):
    real_index = rag_module.rag_service.index_document

    async def _flaky(doc_id, text, metadata, page_starts=None):
        if doc_id == "doc-test-002":
            raise RuntimeError("boom")
        return await real_index(doc_id, text, metadata, page_starts)

    monkeypatch.setattr(rag_module.rag_service, "index_document", _flaky)
    data = (await async_client.post("/api/rag/index-all")).json()
    assert data == {"indexed": 1, "errors": 1, "total": 2, "chunks_indexed": 1}


async def test_stats_do_not_leak_errors(async_client, monkeypatch):
    def _broken():
        raise RuntimeError("sqlite3.OperationalError: /secret/path")

    monkeypatch.setattr(rag_module, "_get_chroma_collection", _broken)
    response = await async_client.get("/api/rag/stats")
    assert response.json()["status"] == "error"
    assert "secret" not in response.text


# --- Embedding model changes -------------------------------------------------------------


async def test_vectors_from_another_embedding_model_are_reported_not_searched(async_client, mock_llm):
    _add_legacy_vectors(1536)

    stats = (await async_client.get("/api/rag/stats")).json()
    assert stats["status"] == "reindex_required"

    response = await async_client.post("/api/rag/query", json={"question": "appendicitis"})
    assert response.status_code == 409
    assert "POST /api/rag/index-all" in response.json()["detail"]

    response = await async_client.post("/api/rag/index/doc-test-001")
    assert response.status_code == 409


async def test_index_all_recovers_from_another_embedding_model(async_client, mock_llm):
    _add_legacy_vectors(1536)

    assert (await async_client.post("/api/rag/index-all")).json()["indexed"] == 2

    assert (await async_client.get("/api/rag/stats")).json()["status"] == "ready"
    data = (await async_client.post("/api/rag/query", json={"question": "appendicitis"})).json()
    assert data["source_documents"][0]["doc_id"] == "doc-test-001"


async def test_collections_record_the_embedding_model(async_client):
    await _index(async_client, "doc-test-001")
    assert rag_module._require_collection().metadata["embedding_model"] == "BAAI/bge-small-en-v1.5"


# --- Query validation ------------------------------------------------------------------


@pytest.mark.parametrize("question", ["", "   ", "x" * 1001])
async def test_query_rejects_blank_or_too_long_questions(async_client, question):
    response = await async_client.post("/api/rag/query", json={"question": question})
    assert response.status_code == 422


async def test_query_accepts_1000_characters(async_client, mock_llm):
    response = await async_client.post("/api/rag/query", json={"question": "x" * 1000})
    assert response.status_code == 200


# --- No fabricated answers -------------------------------------------------------------


async def test_query_without_provider_is_503(async_client):
    await _index(async_client, "doc-test-001")
    response = await async_client.post("/api/rag/query", json={"question": "What was the treatment cost?"})
    assert response.status_code == 503
    assert set(response.json()) == {"detail"}


async def test_query_provider_failure_is_502(async_client, fake_groq, groq_errors):
    await _index(async_client, "doc-test-001")
    fake_groq.respond(groq_errors.connection())
    response = await async_client.post("/api/rag/query", json={"question": "What was the treatment cost?"})
    assert response.status_code == 502
    assert response.json() == {"detail": llm.LLMProviderError.default_detail}


async def test_query_rate_limit_is_502_with_a_retry_hint(async_client, fake_groq, groq_errors):
    await _index(async_client, "doc-test-001")
    fake_groq.respond(groq_errors.rate_limit())
    response = await async_client.post("/api/rag/query", json={"question": "What was the treatment cost?"})
    assert response.status_code == 502
    assert "rate limiting" in response.json()["detail"]


async def test_blank_model_answer_is_502(async_client, fake_groq):
    await _index(async_client, "doc-test-001")
    fake_groq.respond("   ")
    response = await async_client.post("/api/rag/query", json={"question": "What was the treatment cost?"})
    assert response.status_code == 502
    assert response.json() == {"detail": llm.LLMOutputError.default_detail}


async def test_mock_mode_uses_real_retrieval_and_is_labelled(async_client, mock_llm, fake_groq):
    await _index(async_client, "doc-test-001")
    await _index(async_client, "doc-test-002")

    response = await async_client.post("/api/rag/query", json={"question": "appendicitis treatment cost", "top_k": 2})

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "mock"
    assert data["answer"].startswith("[Mock answer")
    assert [s["doc_id"] for s in data["source_documents"]] == ["doc-test-001", "doc-test-002"]
    assert data["source_documents"][0]["filename"] == "invoice_test.pdf"
    assert "Appendicitis" in data["source_documents"][0]["text_snippet"]
    assert data["citations"] == [{"doc_id": "doc-test-001", "filename": "invoice_test.pdf", "pages": []}]
    assert fake_groq.calls == []


async def test_mock_mode_with_empty_index(async_client, mock_llm):
    data = (await async_client.post("/api/rag/query", json={"question": "anything"})).json()
    assert data == {
        "answer": rag_module._NOT_INDEXED_ANSWER,
        "source_documents": [],
        "citations": [],
        "source": "mock",
        "retrieval_mode": settings.RAG_RETRIEVAL_MODE,
    }


async def test_groq_answer_is_grounded_in_retrieved_chunks(async_client, fake_groq):
    await _index(async_client, "doc-test-001")
    await _index(async_client, "doc-test-002")
    fake_groq.respond("The treatment cost was $28,500 [1].")

    response = await async_client.post("/api/rag/query", json={"question": "appendicitis treatment cost", "top_k": 1})

    data = response.json()
    assert data["answer"] == "The treatment cost was $28,500 [1]."
    assert data["source"] == "groq"
    assert [s["doc_id"] for s in data["source_documents"]] == ["doc-test-001"]
    assert data["citations"] == [{"doc_id": "doc-test-001", "filename": "invoice_test.pdf", "pages": []}]
    call = fake_groq.calls[0]
    assert call["model"] == settings.GROQ_MODEL
    system, user = call["messages"]
    assert system["role"] == "system"
    assert "ONLY the numbered context excerpts" in system["content"]
    assert "[1] invoice_test.pdf" in user["content"]
    assert "Treatment Cost: $28,500" in user["content"]
    assert "Jane Smith" not in user["content"]  # top_k=1 keeps the other document out


async def test_citations_name_the_cited_documents_and_pages(async_client, test_db, fake_groq):
    await test_db.documents.update_many({}, {"$set": {"page_count": 1}})
    await _index(async_client, "doc-test-001")
    await _index(async_client, "doc-test-002")
    fake_groq.respond("Jane Smith has Type 2 Diabetes [2], and John Doe had appendicitis [1][7].")

    data = (await async_client.post("/api/rag/query", json={"question": "appendicitis diabetes", "top_k": 2})).json()

    cited = {c["doc_id"]: c for c in data["citations"]}
    assert set(cited) == {"doc-test-001", "doc-test-002"}  # [7] points at no excerpt and is ignored
    assert cited["doc-test-002"] == {"doc_id": "doc-test-002", "filename": "claim_form_test.pdf", "pages": [1]}
    assert all(source["page"] == 1 for source in data["source_documents"])


async def test_groq_query_with_empty_index_does_not_call_the_model(async_client, fake_groq):
    data = (await async_client.post("/api/rag/query", json={"question": "anything"})).json()
    assert data["answer"] == rag_module._NOT_INDEXED_ANSWER
    assert data["citations"] == []
    assert fake_groq.calls == []


async def test_openai_is_tried_first_and_groq_answers_when_it_fails(async_client, fake_openai, fake_groq, groq_errors):
    await _index(async_client, "doc-test-001")
    fake_openai.respond(groq_errors.openai_connection())
    fake_groq.respond("Groq answer [1].")

    data = (await async_client.post("/api/rag/query", json={"question": "appendicitis"})).json()

    assert data["source"] == "groq"
    assert data["answer"] == "Groq answer [1]."
    assert fake_openai.calls[0]["model"] == settings.OPENAI_MODEL


async def test_openai_answers_through_the_same_chain(async_client, fake_openai):
    await _index(async_client, "doc-test-001")
    fake_openai.respond("OpenAI answer [1].")

    data = (await async_client.post("/api/rag/query", json={"question": "appendicitis"})).json()

    assert data["source"] == "openai"
    assert data["citations"][0]["doc_id"] == "doc-test-001"
    assert "[1] invoice_test.pdf" in fake_openai.calls[0]["messages"][1]["content"]


@pytest.mark.parametrize("mode", ["vector", "hybrid"])
async def test_both_retrieval_modes_answer(async_client, monkeypatch, mock_llm, mode):
    monkeypatch.setattr(settings, "RAG_RETRIEVAL_MODE", mode)
    await _index(async_client, "doc-test-001")
    await _index(async_client, "doc-test-002")

    data = (await async_client.post("/api/rag/query", json={"question": "Type 2 Diabetes", "top_k": 2})).json()

    assert data["retrieval_mode"] == mode
    assert data["source_documents"][0]["doc_id"] == "doc-test-002"
    assert all(0.0 <= source["score"] <= 1.0 for source in data["source_documents"])
