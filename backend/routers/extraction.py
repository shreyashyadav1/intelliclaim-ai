"""
IntelliClaim AI - Extraction Router

Endpoints for AI-powered data extraction from documents.
"""

import logging

from fastapi import APIRouter, HTTPException

from db.connection import get_database
from services.claim_service import save_extraction
from services.extraction_service import extraction_service as extractor

logger = logging.getLogger("intelliclaim.extraction")
router = APIRouter()


@router.post("/extract/{document_id}")
async def extract_document(document_id: str):
    """Run AI extraction on a document and create or update its claim.

    Returns 503 when no AI provider is configured and 502 when the provider
    fails; nothing is written in either case.
    """
    db = get_database()
    doc = await db.documents.find_one({"_id": document_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.get("extracted_text"):
        if doc.get("processing_status") == "failed":
            detail = "Text extraction failed for this document, so there is nothing to analyse."
        else:
            detail = "Document has no extracted text. Run OCR first."
        raise HTTPException(status_code=400, detail=detail)

    result = await extractor.extract_claim_data(
        text=doc["extracted_text"],
        document_class=doc.get("document_class", "other"),
    )
    saved = await save_extraction(db, doc, result)

    return {
        "claim_id": saved.claim_id,
        "document_id": document_id,
        "claim_number": saved.claim_number,
        "extracted_data": result.fields.model_dump(),
        # confidence_score is kept for existing clients; it measures field
        # completeness (known fields found / 11), which `completeness` names honestly.
        "confidence_score": result.confidence_score,
        "completeness": result.confidence_score,
        "is_new_claim": saved.is_new_claim,
        "source": result.source,
        "input_truncated": result.input_truncated,
    }


@router.get("/extract/{document_id}/results")
async def get_extraction_results(document_id: str):
    """Get extraction results for a document."""
    db = get_database()
    doc = await db.documents.find_one({"_id": document_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    claim_id = doc.get("claim_id")
    if not claim_id:
        return {"document_id": document_id, "extracted": False, "claim": None}

    claim = await db.claims.find_one({"_id": claim_id})
    if claim:
        claim["id"] = claim.pop("_id")

    return {
        "document_id": document_id,
        "extracted": True,
        "claim": claim,
    }
