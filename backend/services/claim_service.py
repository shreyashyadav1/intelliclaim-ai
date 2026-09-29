"""
IntelliClaim AI - Claim persistence

Creates or updates claims from extraction results while keeping
claims.document_ids and documents.claim_id consistent.

claim_number carries a unique index. Extraction therefore never inserts a
second claim with an existing number (the document is linked to that claim
instead), and a claim whose documents contain no claim number gets a
placeholder such as UNASSIGNED-3F9A2B7C1D, flagged with
claim_number_is_placeholder so validation still treats it as missing.
"""

import logging
from dataclasses import dataclass
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from models.extraction import CLAIM_FIELDS
from services.extraction_service import ExtractionResult
from utils.helpers import generate_id, utc_now

logger = logging.getLogger("intelliclaim.claims")

PLACEHOLDER_PREFIX = "UNASSIGNED-"
_PLACEHOLDER_ATTEMPTS = 3


@dataclass(frozen=True)
class SavedExtraction:
    claim_id: str
    claim_number: str
    is_new_claim: bool


def new_placeholder_claim_number() -> str:
    return f"{PLACEHOLDER_PREFIX}{generate_id()[:10].upper()}"


def claim_completeness(claim: dict[str, Any]) -> float:
    """Share of the eleven claim fields present on a stored claim (placeholders excluded)."""
    filled = 0
    for name in CLAIM_FIELDS:
        value = claim.get(name)
        if value is None or value == "":
            continue
        if name == "claim_number" and claim.get("claim_number_is_placeholder"):
            continue
        filled += 1
    return round(filled / len(CLAIM_FIELDS), 2)


async def save_extraction(
    db: AsyncIOMotorDatabase, document: dict[str, Any], result: ExtractionResult
) -> SavedExtraction:
    """Store an extraction result and link the document to its claim.

    - The document is already linked to a claim: update that claim (new values win).
    - Another claim has the extracted claim number: link to it and fill its empty fields.
    - Otherwise: create a claim, with a placeholder number if none was extracted.
    """
    fields = result.fields.model_dump()
    document_id = document["_id"]

    linked_id = document.get("claim_id")
    if linked_id:
        claim = await db.claims.find_one({"_id": linked_id})
        if claim is not None:
            return await _merge_into_claim(db, claim, fields, document_id, result.source, overwrite=True)
        logger.warning("Document %s is linked to missing claim %s; linking it again", document_id, linked_id)

    if fields["claim_number"]:
        claim = await db.claims.find_one({"claim_number": fields["claim_number"]})
        if claim is not None:
            return await _merge_into_claim(db, claim, fields, document_id, result.source, overwrite=False)

    return await _create_claim(db, fields, document_id, result.source)


async def _create_claim(
    db: AsyncIOMotorDatabase, fields: dict[str, Any], document_id: str, source: str
) -> SavedExtraction:
    has_number = fields["claim_number"] is not None
    for _ in range(_PLACEHOLDER_ATTEMPTS):
        now = utc_now()
        record = {
            "_id": generate_id(),
            **fields,
            "claim_number": fields["claim_number"] if has_number else new_placeholder_claim_number(),
            "claim_number_is_placeholder": not has_number,
            "status": "pending",
            "risk_score": 0.0,
            "risk_flags": [],
            "document_ids": [document_id],
            "extraction_source": source,
            "created_at": now,
            "updated_at": now,
        }
        record["extraction_confidence"] = claim_completeness(record)
        try:
            await db.claims.insert_one(record)
        except DuplicateKeyError:
            if not has_number:
                continue  # placeholder collision: try another placeholder
            # A concurrent request created this claim number first: link to that claim.
            existing = await db.claims.find_one({"claim_number": fields["claim_number"]})
            if existing is None:
                raise
            return await _merge_into_claim(db, existing, fields, document_id, source, overwrite=False)

        await _link_document(db, document_id, record["_id"])
        logger.info("Created claim %s (%s) from document %s", record["_id"], record["claim_number"], document_id)
        return SavedExtraction(record["_id"], record["claim_number"], True)

    raise RuntimeError("Could not allocate a unique placeholder claim number")


async def _merge_into_claim(
    db: AsyncIOMotorDatabase,
    claim: dict[str, Any],
    fields: dict[str, Any],
    document_id: str,
    source: str,
    *,
    overwrite: bool,
) -> SavedExtraction:
    """Apply extracted values to an existing claim.

    overwrite=True is a re-extraction of a document already linked to the claim,
    so non-empty new values replace old ones. overwrite=False is another document
    for the same claim, so it only fills fields that are still empty.
    """
    updates: dict[str, Any] = {}
    for name, value in fields.items():
        if value is None or name == "claim_number":
            continue
        if overwrite or claim.get(name) in (None, ""):
            updates[name] = value

    new_number = fields["claim_number"]
    may_rename = overwrite or claim.get("claim_number_is_placeholder")
    if new_number and new_number != claim.get("claim_number") and may_rename:
        clash = await db.claims.find_one({"claim_number": new_number, "_id": {"$ne": claim["_id"]}}, {"_id": 1})
        if clash is None:
            updates["claim_number"] = new_number
            updates["claim_number_is_placeholder"] = False
        else:
            logger.warning(
                "Keeping claim number %s on claim %s: %s belongs to claim %s",
                claim.get("claim_number"), claim["_id"], new_number, clash["_id"],
            )

    try:
        await _apply_update(db, claim, updates, document_id, source)
    except DuplicateKeyError:
        # Lost a race for the new claim number; keep the current one.
        updates.pop("claim_number", None)
        updates.pop("claim_number_is_placeholder", None)
        await _apply_update(db, claim, updates, document_id, source)

    await _link_document(db, document_id, claim["_id"])
    claim_number = updates.get("claim_number", claim.get("claim_number"))
    logger.info("Updated claim %s from document %s", claim["_id"], document_id)
    return SavedExtraction(claim["_id"], claim_number, False)


async def _apply_update(
    db: AsyncIOMotorDatabase, claim: dict[str, Any], updates: dict[str, Any], document_id: str, source: str
) -> None:
    changes = {
        **updates,
        "extraction_confidence": claim_completeness({**claim, **updates}),
        "extraction_source": source,
        "updated_at": utc_now(),
    }
    await db.claims.update_one(
        {"_id": claim["_id"]},
        {"$set": changes, "$addToSet": {"document_ids": document_id}},
    )


async def _link_document(db: AsyncIOMotorDatabase, document_id: str, claim_id: str) -> None:
    await db.documents.update_one(
        {"_id": document_id},
        {"$set": {"claim_id": claim_id, "updated_at": utc_now()}},
    )


async def detach_document(db: AsyncIOMotorDatabase, document_id: str) -> int:
    """Remove a deleted document from every claim that lists it; returns claims changed."""
    result = await db.claims.update_many(
        {"document_ids": document_id},
        {"$pull": {"document_ids": document_id}, "$set": {"updated_at": utc_now()}},
    )
    return result.modified_count


async def detach_claim_documents(db: AsyncIOMotorDatabase, claim_id: str) -> int:
    """Unlink the documents of a deleted claim; returns documents changed."""
    result = await db.documents.update_many(
        {"claim_id": claim_id},
        {"$set": {"claim_id": None, "updated_at": utc_now()}},
    )
    return result.modified_count
