"""
IntelliClaim AI - RAG Router Tests

Retrieval runs against a per-test ChromaDB with the fake embedder; answers
come from FakeGroq or MOCK_LLM, never from a real provider.
"""

import pytest

import services.rag_service as rag_module
from services import llm


async def _index(async_client, doc_id: str) -> dict:
    response = await async_client.post(f"/api/rag/index/{doc_id}")
    assert response.status_code == 200, response.text
    return response.json()


# --- Indexing ------------------------------------------------------------------------


async def test_index_document_stores_chunks(async_client):
    data = await _index(async_client, "doc-test-001")
    assert data == {"success": True, "document_id": "doc-test-001", "chunks_indexed": 1}

    stats = (await async_client.get("/api/rag/stats")).json()
    assert stats == {"indexed_chunks": 1, "status": "ready"}


async def test_index_document_not_found(async_client):
    assert (await async_client.post("/api/rag/index/nonexistent")).status_code == 404


async def test_index_document_without_text_is_400(async_client, test_db):
    await test_db.documents.update_one({"_id": "doc-test-001"}, {"$set": {"extracted_text": None}})
    assert (await async_client.post("/api/rag/index/doc-test-001")).status_code == 400


async def test_index_failure_is_a_generic_500(async_client, monkeypatch):
    def _broken_embed(texts):
        raise RuntimeError("onnxruntime: secret internal path /opt/model")

    monkeypatch.setattr(rag_module, "_embed", _broken_embed)
    response = await async_client.post("/api/rag/index/doc-test-001")
    assert response.status_code == 500
    assert response.json() == {"detail": "Failed to index the document"}


async def test_index_all_counts_indexed_documents(async_client, test_db):
    await test_db.documents.insert_one({
        "_id": "doc-failed", "processing_status": "failed", "extracted_text": "", "error_message": "No text",
    })
    data = (await async_client.post("/api/rag/index-all")).json()
    assert data == {"indexed": 2, "errors": 0, "total": 2}


async def test_index_all_reports_failures(async_client, monkeypatch):
    real_index = rag_module.rag_service.index_document

    async def _flaky(doc_id, text, metadata):
        if doc_id == "doc-test-002":
            raise RuntimeError("boom")
        return await real_index(doc_id, text, metadata)

    monkeypatch.setattr(rag_module.rag_service, "index_document", _flaky)
    data = (await async_client.post("/api/rag/index-all")).json()
    assert data == {"indexed": 1, "errors": 1, "total": 2}


async def test_stats_do_not_leak_errors(async_client, monkeypatch):
    def _broken():
        raise RuntimeError("sqlite3.OperationalError: /secret/path")

    monkeypatch.setattr(rag_module, "_get_chroma_collection", _broken)
    response = await async_client.get("/api/rag/stats")
    assert response.json() == {"indexed_chunks": 0, "status": "error"}


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
    assert fake_groq.calls == []


async def test_mock_mode_with_empty_index(async_client, mock_llm):
    data = (await async_client.post("/api/rag/query", json={"question": "anything"})).json()
    assert data == {"answer": rag_module._NOT_INDEXED_ANSWER, "source_documents": [], "source": "mock"}


async def test_groq_answer_is_grounded_in_retrieved_chunks(async_client, fake_groq):
    await _index(async_client, "doc-test-001")
    await _index(async_client, "doc-test-002")
    fake_groq.respond("The treatment cost was $28,500.")

    response = await async_client.post("/api/rag/query", json={"question": "appendicitis treatment cost", "top_k": 1})

    data = response.json()
    assert data["answer"] == "The treatment cost was $28,500."
    assert data["source"] == "groq"
    assert [s["doc_id"] for s in data["source_documents"]] == ["doc-test-001"]
    system, user = fake_groq.calls[0]["messages"]
    assert system["role"] == "system"
    assert "Treatment Cost: $28,500" in user["content"]
    assert "Jane Smith" not in user["content"]  # top_k=1 keeps the other document out


async def test_groq_query_with_empty_index_does_not_call_the_model(async_client, fake_groq):
    data = (await async_client.post("/api/rag/query", json={"question": "anything"})).json()
    assert data["answer"] == rag_module._NOT_INDEXED_ANSWER
    assert fake_groq.calls == []
