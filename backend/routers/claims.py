"""
IntelliClaim AI - Claims Router

Endpoints for CRUD operations on insurance claims.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.connection import get_database
from utils.helpers import utc_now

logger = logging.getLogger("intelliclaim.claims")
router = APIRouter()


@router.get("/claims")
async def list_claims(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    risk_level: Optional[str] = None,
    search: Optional[str] = None,
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

    if search:
        query["$or"] = [
            {"claim_number": {"$regex": search, "$options": "i"}},
            {"policy_number": {"$regex": search, "$options": "i"}},
            {"patient_name": {"$regex": search, "$options": "i"}},
            {"diagnosis": {"$regex": search, "$options": "i"}},
        ]

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
async def update_claim(claim_id: str, updates: dict):
    """Update a claim's fields."""
    db = get_database()
    existing = await db.claims.find_one({"_id": claim_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Claim not found")

    # Filter out None values and _id/id
    clean_updates = {k: v for k, v in updates.items() if v is not None and k not in ("_id", "id")}
    clean_updates["updated_at"] = utc_now()

    await db.claims.update_one({"_id": claim_id}, {"$set": clean_updates})

    updated = await db.claims.find_one({"_id": claim_id})
    updated["id"] = updated.pop("_id")
    return updated


@router.delete("/claims/{claim_id}")
async def delete_claim(claim_id: str):
    """Delete a claim."""
    db = get_database()
    result = await db.claims.delete_one({"_id": claim_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Claim not found")
    return {"message": "Claim deleted", "id": claim_id}


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
