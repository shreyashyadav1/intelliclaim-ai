"""
IntelliClaim AI - Claims Router

Endpoints for CRUD operations on insurance claims.
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pymongo.errors import DuplicateKeyError

from db.connection import get_database
from models.claim import ClaimUpdate
from security import WRITE_LIMIT, limiter, require_admin_key
from services.claim_service import detach_claim_documents
from utils.helpers import utc_now

logger = logging.getLogger("intelliclaim.claims")
router = APIRouter()

_SEARCH_FIELDS = ("claim_number", "policy_number", "patient_name", "diagnosis")


@router.get("/claims")
async def list_claims(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = None,
    risk_level: str | None = None,
    search: str | None = Query(None, max_length=100),
):
    """List claims with optional filters and pagination."""
    db = get_database()
    query = {}

    if status:
        query["status"] = status

    if risk_level:
        if risk_level == "low":
            query["risk_score"] = {"$lt": 30}
        elif risk_level == "medium":
            query["risk_score"] = {"$gte": 30, "$lt": 60}
        elif risk_level == "high":
            query["risk_score"] = {"$gte": 60}

    if search and search.strip():
        # Escape the input so it is matched literally rather than run as a regex.
        pattern = {"$regex": re.escape(search.strip()), "$options": "i"}
        query["$or"] = [{field: pattern} for field in _SEARCH_FIELDS]

    cursor = db.claims.find(query).sort("created_at", -1).skip(skip).limit(limit)
    claims = await cursor.to_list(length=limit)
    total = await db.claims.count_documents(query)

    for claim in claims:
        claim["id"] = claim.pop("_id")

    return {"claims": claims, "total": total, "skip": skip, "limit": limit}


@router.get("/claims/{claim_id}")
async def get_claim(claim_id: str):
    """Get a single claim by ID."""
    db = get_database()
    claim = await db.claims.find_one({"_id": claim_id})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    claim["id"] = claim.pop("_id")
    return claim


@router.put("/claims/{claim_id}")
@limiter.limit(WRITE_LIMIT)
async def update_claim(request: Request, claim_id: str, updates: ClaimUpdate):
    """Update a claim's fields. Only fields defined on ClaimUpdate are accepted."""
    db = get_database()
    existing = await db.claims.find_one({"_id": claim_id}, {"_id": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Claim not found")

    changes = updates.model_dump(mode="json", exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No updatable fields were provided")
    if "claim_number" in changes:
        changes["claim_number_is_placeholder"] = False
    changes["updated_at"] = utc_now()

    try:
        await db.claims.update_one({"_id": claim_id}, {"$set": changes})
    except DuplicateKeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Claim number {changes['claim_number']} is already used by another claim",
        ) from None

    updated = await db.claims.find_one({"_id": claim_id})
    updated["id"] = updated.pop("_id")
    return updated


@router.delete("/claims/{claim_id}", dependencies=[Depends(require_admin_key)])
@limiter.limit(WRITE_LIMIT)
async def delete_claim(request: Request, claim_id: str):
    """Delete a claim and unlink its documents (the documents themselves are kept)."""
    db = get_database()
    result = await db.claims.delete_one({"_id": claim_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Claim not found")
    unlinked_documents = await detach_claim_documents(db, claim_id)
    return {"message": "Claim deleted", "id": claim_id, "unlinked_documents": unlinked_documents}


@router.get("/claims/{claim_id}/documents")
async def get_claim_documents(claim_id: str):
    """Get all documents associated with a claim."""
    db = get_database()
    claim = await db.claims.find_one({"_id": claim_id})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    doc_ids = claim.get("document_ids", [])
    if not doc_ids:
        return {"documents": []}

    cursor = db.documents.find({"_id": {"$in": doc_ids}})
    docs = await cursor.to_list(length=100)
    for doc in docs:
        doc["id"] = doc.pop("_id")
        if doc.get("extracted_text"):
            doc["extracted_text_preview"] = doc["extracted_text"][:200]
            del doc["extracted_text"]

    return {"documents": docs}
