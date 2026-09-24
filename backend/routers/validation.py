"""
IntelliClaim AI - Validation Router

Endpoints for claim validation, risk detection, and flagged claims.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints

from db.connection import get_database
from services.llm import LLMError
from services.validation_service import validation_service as validator
from utils.helpers import utc_now

logger = logging.getLogger("intelliclaim.validation")
router = APIRouter()

MAX_BATCH_SIZE = 100

ClaimId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class BatchValidateRequest(BaseModel):
    claim_ids: list[ClaimId] = Field(min_length=1, max_length=MAX_BATCH_SIZE)


async def _store_result(db, claim_id: str, result: dict) -> None:
    update_data = {
        "risk_score": result["risk_score"],
        "risk_flags": [f["description"] for f in result["flags"]],
        "updated_at": utc_now(),
    }
    if result["risk_level"] == "high":
        update_data["status"] = "flagged"
    await db.claims.update_one({"_id": claim_id}, {"$set": update_data})


@router.post("/validate/{claim_id}")
async def validate_claim(claim_id: str):
    """Run validation on a single claim and update its risk score/flags.

    If the AI provider fails the request returns 502 and the claim is left unchanged.
    """
    db = get_database()
    claim = await db.claims.find_one({"_id": claim_id})
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    result = await validator.validate_claim(claim)
    await _store_result(db, claim_id, result)

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


@router.post("/batch-validate")
async def batch_validate(payload: BatchValidateRequest):
    """Validate up to 100 claims.

    Each claim gets its own result entry. If the AI provider fails, the
    remaining claims are skipped (so an outage is not retried 100 times) and
    the request fails with 502 only when no claim could be validated.
    """
    db = get_database()
    claim_ids = list(dict.fromkeys(payload.claim_ids))  # de-duplicate, keep order
    results = []
    validated = 0
    provider_error: LLMError | None = None

    for claim_id in claim_ids:
        if provider_error is not None:
            results.append({"claim_id": claim_id, "error": "Skipped because the AI provider is unavailable"})
            continue

        claim = await db.claims.find_one({"_id": claim_id})
        if not claim:
            results.append({"claim_id": claim_id, "error": "Not found"})
            continue

        try:
            result = await validator.validate_claim(claim)
        except LLMError as exc:
            provider_error = exc
            results.append({"claim_id": claim_id, "error": exc.detail})
            continue

        await _store_result(db, claim_id, result)
        results.append({"claim_id": claim_id, **result})
        validated += 1

    if provider_error is not None and validated == 0:
        raise provider_error

    return {
        "results": results,
        "total_validated": validated,
        "total_requested": len(claim_ids),
        "errors": len(results) - validated,
    }
