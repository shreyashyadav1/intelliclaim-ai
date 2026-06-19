"""
IntelliClaim AI - RAG Router

Endpoints for Retrieval-Augmented Generation search across claim documents.
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db.connection import get_database
from services.rag_service import RAGService

logger = logging.getLogger("intelliclaim.rag")
router = APIRouter()
rag_service = RAGService()


class QueryRequest(BaseModel):
    """RAG query request."""
    question: str = Field(..., min_length=1, description="Natural language question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")


@router.post("/rag/query")
async def rag_query(request: QueryRequest):
    """Query documents using RAG (natural language search)."""
    try:
        result = await rag_service.query(request.question, top_k=request.top_k)
        return result
    except Exception as e:
        logger.error(f"RAG query failed: {e}")
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")


@router.post("/rag/index/{document_id}")
async def index_document(document_id: str):
    """Index a single document for RAG search."""
    db = get_database()
    doc = await db.documents.find_one({"_id": document_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.get("extracted_text"):
        raise HTTPException(status_code=400, detail="Document has no extracted text")

    try:
        metadata = {
            "filename": doc.get("filename", ""),
            "document_class": doc.get("document_class", "other"),
            "claim_id": doc.get("claim_id", ""),
        }
        success = await rag_service.index_document(document_id, doc["extracted_text"], metadata)
        return {"success": success, "document_id": document_id}
    except Exception as e:
        logger.error(f"Indexing failed for {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")


@router.post("/rag/index-all")
async def index_all_documents():
    """Re-index all processed documents."""
    db = get_database()
    cursor = db.documents.find({"processing_status": "processed", "extracted_text": {"$ne": None}})
    docs = await cursor.to_list(length=10000)

    indexed = 0
    errors = 0
    for doc in docs:
        try:
            metadata = {
                "filename": doc.get("filename", ""),
                "document_class": doc.get("document_class", "other"),
                "claim_id": doc.get("claim_id", ""),
            }
            await rag_service.index_document(doc["_id"], doc["extracted_text"], metadata)
            indexed += 1
        except Exception as e:
            logger.warning(f"Failed to index {doc['_id']}: {e}")
            errors += 1

    return {"indexed": indexed, "errors": errors, "total": len(docs)}


@router.get("/rag/stats")
async def get_rag_stats():
    """Get RAG index statistics."""
    try:
        stats = await rag_service.get_index_stats()
        return stats
    except Exception as e:
        logger.error(f"Failed to get RAG stats: {e}")
        return {"indexed_documents": 0, "status": "unavailable"}
