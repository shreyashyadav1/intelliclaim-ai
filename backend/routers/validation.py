"""
IntelliClaim AI - Validation Router

Endpoints for claim validation, risk detection, and flagged claims.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_database
from services.validation_service import ValidationService
from utils.helpers import utc_now

logger = logging.getLogger("intelliclaim.validation")
router = APIRouter()
validator = ValidationService()


class BatchValidateRequest(BaseModel):
    claim_ids: list[str]


@router.post("/validate/{claim_id}")
async def validate_claim(claim_id: str):
    """Run validation on a single claim and update its risk score/flags."""
    db = get_database()
    claim = await db.claims.find_one({"_id": claim_id})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    result = await validator.validate_claim(claim)

    # Update claim with risk assessment
    update_data = {
        "risk_score": result["risk_score"],
        "risk_flags": [f["description"] for f in result["flags"]],
        "updated_at": utc_now(),
    }
    if result["risk_level"] == "high":
        update_data["status"] = "flagged"

    await db.claims.update_one({"_id": claim_id}, {"$set": update_data})

    return {
        "claim_id": claim_id,
        **result,
    }


@router.get("/validate/flagged")
async def get_flagged_claims(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """Get all flagged/high-risk claims."""
    db = get_database()
    query = {"$or": [{"status": "flagged"}, {"risk_score": {"$gte": 30}}]}

    cursor = db.claims.find(query).sort("risk_score", -1).skip(skip).limit(limit)
    claims = await cursor.to_list(length=limit)
    total = await db.claims.count_documents(query)

    for claim in claims:
        claim["id"] = claim.pop("_id")

    return {"claims": claims, "total": total, "skip": skip, "limit": limit}


@router.post("/validate/batch")
async def batch_validate(request: BatchValidateRequest):
    """Validate multiple claims in batch."""
    db = get_database()
    results = []

    for claim_id in request.claim_ids:
        claim = await db.claims.find_one({"_id": claim_id})
        if not claim:
            results.append({"claim_id": claim_id, "error": "Not found"})
            continue

        result = await validator.validate_claim(claim)

        update_data = {
            "risk_score": result["risk_score"],
            "risk_flags": [f["description"] for f in result["flags"]],
            "updated_at": utc_now(),
        }
        if result["risk_level"] == "high":
            update_data["status"] = "flagged"

        await db.claims.update_one({"_id": claim_id}, {"$set": update_data})
        results.append({"claim_id": claim_id, **result})

    return {"results": results, "total_validated": len(results)}
