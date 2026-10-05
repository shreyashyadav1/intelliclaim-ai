"""
IntelliClaim AI - Claim Data Models

Request models for insurance claims.
"""

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints


class ClaimStatus(StrEnum):
    """Possible states of an insurance claim."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"


def _require_iso_date(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("Dates must use the YYYY-MM-DD format") from exc


_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
_IsoDate = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_require_iso_date)]
_FlagText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ClaimUpdate(BaseModel):
    """Fields a client may change through PUT /api/claims/{id}. All optional.

    Unknown keys (including _id, id and timestamps) are ignored. Document links
    are not editable here: they are maintained by extraction and deletes, which
    keep claims.document_ids and documents.claim_id consistent.
    """
    policy_number: _Text | None = None
    claim_number: _Text | None = None
    patient_name: _Text | None = None
    diagnosis: _Text | None = None
    treatment_cost: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    hospital_name: _Text | None = None
    hospital_address: _Text | None = None
    provider_id: _Text | None = None
    date_of_service: _IsoDate | None = None
    date_of_admission: _IsoDate | None = None
    date_of_discharge: _IsoDate | None = None
    status: ClaimStatus | None = None
    risk_score: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    risk_flags: list[_FlagText] | None = Field(default=None, max_length=50)
    extraction_confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
