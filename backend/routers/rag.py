"""
IntelliClaim AI - RAG Router

Endpoints for Retrieval-Augmented Generation search across claim documents.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from db.connection import get_database
from services.llm import LLMError
from services.rag_service import rag_service

logger = logging.getLogger("intelliclaim.rag")
router = APIRouter()

MAX_QUESTION_LENGTH = 1000


class QueryRequest(BaseModel):
    """RAG query request."""
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH)] = (
        Field(..., description="Natural language question (at most 1,000 characters)")
    )
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")


def _index_metadata(doc: dict) -> dict:
    return {
        "filename": doc.get("filename", ""),
        "document_class": doc.get("document_class", "other"),
        "claim_id": doc.get("claim_id") or "",
    }


@router.post("/rag/query")
async def rag_query(payload: QueryRequest):
    """Query documents using RAG (natural language search).

    503 when no AI provider is configured, 502 when the provider fails.
    """
    return await rag_service.query(payload.question, top_k=payload.top_k)


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
        chunks = await rag_service.index_document(document_id, doc["extracted_text"], _index_metadata(doc))
    except LLMError:
        raise
    except Exception:
        logger.exception("Indexing failed for %s", document_id)
        raise HTTPException(status_code=500, detail="Failed to index the document") from None
    return {"success": chunks > 0, "document_id": document_id, "chunks_indexed": chunks}


@router.post("/rag/index-all")
async def index_all_documents():
    """Re-index all processed documents."""
    db = get_database()
    cursor = db.documents.find({"processing_status": "processed", "extracted_text": {"$nin": [None, ""]}})
    docs = await cursor.to_list(length=10000)

    indexed = 0
    errors = 0
    for position, doc in enumerate(docs):
        try:
            chunks = await rag_service.index_document(doc["_id"], doc["extracted_text"], _index_metadata(doc))
        except LLMError as exc:
            # The embedding provider is down; the remaining documents would fail too.
            logger.warning("Stopping re-index at %s: %s", doc["_id"], exc.detail)
            errors += len(docs) - position
            break
        except Exception:
            logger.exception("Failed to index %s", doc["_id"])
            errors += 1
            continue
        if chunks:
            indexed += 1
        else:
            errors += 1

    return {"indexed": indexed, "errors": errors, "total": len(docs)}


@router.get("/rag/stats")
async def get_rag_stats():
    """Get RAG index statistics."""
    return await rag_service.get_index_stats()
