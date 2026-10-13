"""
IntelliClaim AI - RAG Router

Endpoints for Retrieval-Augmented Generation search across claim documents.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, StringConstraints

from db.connection import get_database
from security import BULK_LIMIT, SEARCH_LIMIT, WRITE_LIMIT, limiter, require_admin_key
from services.llm import LLMError
from services.rag_errors import IncompatibleIndexError
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


def _page_starts(doc: dict) -> list[int] | None:
    """Page offsets stored at upload; a one-page document without them starts page 1 at 0."""
    if doc.get("page_starts"):
        return doc["page_starts"]
    return [0] if doc.get("page_count") == 1 else None


async def _index(doc: dict) -> int:
    return await rag_service.index_document(
        doc["_id"], doc["extracted_text"], _index_metadata(doc), page_starts=_page_starts(doc)
    )


@router.post("/rag/query")
@limiter.limit(SEARCH_LIMIT)
async def rag_query(request: Request, payload: QueryRequest):
    """Query documents using RAG (natural language search).

    503 when no AI provider is configured, 502 when the provider fails and 409
    when the index was built with another embedding model (rebuild it with
    POST /api/rag/index-all).
    """
    return await rag_service.query(payload.question, top_k=payload.top_k)


@router.post("/rag/index/{document_id}")
@limiter.limit(WRITE_LIMIT)
async def index_document(request: Request, document_id: str):
    """Index a single document for RAG search."""
    db = get_database()
    doc = await db.documents.find_one({"_id": document_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.get("extracted_text"):
        raise HTTPException(status_code=400, detail="Document has no extracted text")

    try:
        chunks = await _index(doc)
    except (LLMError, IncompatibleIndexError):
        raise
    except Exception:
        logger.exception("Indexing failed for %s", document_id)
        raise HTTPException(status_code=500, detail="Failed to index the document") from None
    return {"success": chunks > 0, "document_id": document_id, "chunks_indexed": chunks}


@router.post("/rag/index-all", dependencies=[Depends(require_admin_key)])
@limiter.limit(BULK_LIMIT)
async def index_all_documents(request: Request):
    """Rebuild the search index from every processed document.

    The collection is replaced first, which also clears vectors left behind by
    an earlier embedding model or chunking, then each document is re-indexed.
    """
    db = get_database()
    cursor = db.documents.find({"processing_status": "processed", "extracted_text": {"$nin": [None, ""]}})
    docs = await cursor.to_list(length=10000)

    await rag_service.reset_index()
    indexed = 0
    errors = 0
    chunks_indexed = 0
    for doc in docs:
        try:
            chunks = await _index(doc)
        except Exception:
            logger.exception("Failed to index %s", doc["_id"])
            errors += 1
            continue
        if chunks:
            indexed += 1
            chunks_indexed += chunks
        else:
            errors += 1

    logger.info("Rebuilt the search index: %d of %d documents, %d chunks", indexed, len(docs), chunks_indexed)
    return {"indexed": indexed, "errors": errors, "total": len(docs), "chunks_indexed": chunks_indexed}


@router.get("/rag/stats")
async def get_rag_stats():
    """Get RAG index statistics."""
    return await rag_service.get_index_stats()
