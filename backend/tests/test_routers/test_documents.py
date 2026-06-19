"""
IntelliClaim AI — Documents Router Tests

Tests document listing, retrieval, and filtering.
"""

import pytest


@pytest.mark.asyncio
async def test_list_documents(async_client):
    """GET /api/documents returns the seeded documents."""
    response = await async_client.get("/api/documents")
    assert response.status_code == 200

    data = response.json()
    assert "documents" in data
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_list_documents_by_class(async_client):
    """Document class filter works."""
    response = await async_client.get("/api/documents?document_class=invoice")
    assert response.status_code == 200

    data = response.json()
    for doc in data["documents"]:
        assert doc["document_class"] == "invoice"


@pytest.mark.asyncio
async def test_get_document_by_id(async_client):
    """GET /api/documents/{id} returns the correct document."""
    response = await async_client.get("/api/documents/doc-test-001")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == "doc-test-001"
    assert data["filename"] == "invoice_test.pdf"


@pytest.mark.asyncio
async def test_get_document_not_found(async_client):
    """GET /api/documents/{id} returns 404 for unknown ID."""
    response = await async_client.get("/api/documents/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_document(async_client):
    """DELETE /api/documents/{id} removes the document."""
    response = await async_client.delete("/api/documents/doc-test-001")
    assert response.status_code == 200

    # Verify it's gone
    response = await async_client.get("/api/documents/doc-test-001")
    assert response.status_code == 404
