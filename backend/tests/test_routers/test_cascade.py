"""Deleting documents and claims keeps vectors and links consistent."""

import services.rag_service as rag_module


def _vector_count(doc_id: str) -> int:
    return len(rag_module._require_collection().get(where={"doc_id": doc_id}, include=[])["ids"])


async def test_deleting_a_document_removes_vectors_links_and_file(async_client, test_db, storage_dir):
    stored_file = storage_dir / "documents" / "abc_claim_form.pdf"
    stored_file.parent.mkdir(parents=True)
    stored_file.write_bytes(b"%PDF-1.7")
    await test_db.documents.update_one({"_id": "doc-test-002"}, {"$set": {"storage_path": str(stored_file)}})
    await async_client.post("/api/rag/index/doc-test-002")
    assert _vector_count("doc-test-002") == 1

    response = await async_client.delete("/api/documents/doc-test-002")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Document deleted",
        "id": "doc-test-002",
        "vectors_removed": 1,
        "unlinked_claims": 1,
    }
    assert _vector_count("doc-test-002") == 0
    assert (await test_db.claims.find_one({"_id": "claim-test-001"}))["document_ids"] == []
    assert await test_db.documents.find_one({"_id": "doc-test-002"}) is None
    assert not stored_file.exists()
    documents = (await async_client.get("/api/claims/claim-test-001/documents")).json()["documents"]
    assert documents == []


async def test_deleted_documents_disappear_from_search(async_client, mock_llm):
    await async_client.post("/api/rag/index/doc-test-001")
    await async_client.delete("/api/documents/doc-test-001")

    data = (await async_client.post("/api/rag/query", json={"question": "appendicitis"})).json()
    assert data["source_documents"] == []


async def test_vector_store_failure_deletes_nothing(async_client, test_db, monkeypatch):
    def _unavailable():
        raise RuntimeError("chroma is down")

    monkeypatch.setattr(rag_module, "_get_chroma_collection", _unavailable)
    response = await async_client.delete("/api/documents/doc-test-002")

    assert response.status_code == 500
    assert await test_db.documents.find_one({"_id": "doc-test-002"}) is not None
    assert (await test_db.claims.find_one({"_id": "claim-test-001"}))["document_ids"] == ["doc-test-002"]


async def test_deleting_a_claim_unlinks_its_documents(async_client, test_db):
    response = await async_client.delete("/api/claims/claim-test-001")

    assert response.status_code == 200
    assert response.json() == {"message": "Claim deleted", "id": "claim-test-001", "unlinked_documents": 1}
    document = await test_db.documents.find_one({"_id": "doc-test-002"})
    assert document is not None
    assert document["claim_id"] is None
    results = (await async_client.get("/api/extract/doc-test-002/results")).json()
    assert results["extracted"] is False


async def test_deleting_a_missing_claim_is_404(async_client):
    assert (await async_client.delete("/api/claims/nonexistent")).status_code == 404
