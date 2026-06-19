"""
IntelliClaim AI - Extraction Router

Endpoints for AI-powered data extraction from documents.
"""

import logging

from fastapi import APIRouter, HTTPException

from db.connection import get_database
from services.extraction_service import ExtractionService
from utils.helpers import generate_id, utc_now

logger = logging.getLogger("intelliclaim.extraction")
router = APIRouter()
extractor = ExtractionService()


@router.post("/extract/{document_id}")
async def extract_document(document_id: str):
    """Run AI extraction on a document and create/update a claim."""
    db = get_database()
    doc = await db.documents.find_one({"_id": document_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not doc.get("extracted_text"):
        raise HTTPException(status_code=400, detail="Document has no extracted text. Run OCR first.")

    try:
        # Extract claim data using AI
        extraction_result = await extractor.extract_claim_data(
            text=doc["extracted_text"],
            document_class=doc.get("document_class", "other"),
        )

        extracted = extraction_result.get("extracted_data", {})
        confidence = extraction_result.get("confidence_score", 0.0)

        # Check if claim already exists for this document
        existing_claim_id = doc.get("claim_id")
        if existing_claim_id:
            # Update existing claim
            update_data = {**extracted, "extraction_confidence": confidence, "updated_at": utc_now()}
            await db.claims.update_one({"_id": existing_claim_id}, {"$set": update_data})
            claim_id = existing_claim_id
            logger.info(f"Updated claim {claim_id} from document {document_id}")
        else:
            # Create new claim
            claim_id = generate_id()
            claim_record = {
                "_id": claim_id,
                **extracted,
                "status": "pending",
                "risk_score": 0.0,
                "risk_flags": [],
                "document_ids": [document_id],
                "extraction_confidence": confidence,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            await db.claims.insert_one(claim_record)

            # Link document to claim
            await db.documents.update_one(
                {"_id": document_id},
                {"$set": {"claim_id": claim_id, "updated_at": utc_now()}},
            )
            logger.info(f"Created claim {claim_id} from document {document_id}")

        return {
            "claim_id": claim_id,
            "document_id": document_id,
            "extracted_data": extracted,
            "confidence_score": confidence,
            "is_new_claim": existing_claim_id is None,
        }

    except Exception as e:
        logger.error(f"Extraction failed for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


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
