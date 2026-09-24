"""
IntelliClaim AI - Claim Data Models

Pydantic v2 models for insurance claim data throughout the application lifecycle:
create, read, update, and database representation.
"""

from datetime import date, datetime
from enum import Enum
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from utils.helpers import generate_id, utc_now


class ClaimStatus(str, Enum):
    """Possible states of an insurance claim."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"


class ClaimBase(BaseModel):
    """Core fields shared across all claim representations."""
    policy_number: str = Field(..., min_length=1, description="Insurance policy number")
    claim_number: str = Field(..., min_length=1, description="Unique claim reference number")
    patient_name: str = Field(..., min_length=1, description="Full name of the patient")
    diagnosis: str = Field(..., min_length=1, description="Primary diagnosis or ICD code")
    treatment_cost: float = Field(..., ge=0, description="Total treatment cost in USD")
    hospital_name: str = Field(..., min_length=1, description="Name of the treating hospital")
    hospital_address: Optional[str] = Field(default=None, description="Hospital street address")
    provider_id: Optional[str] = Field(default=None, description="Healthcare provider / NPI identifier")
    date_of_service: Optional[str] = Field(default=None, description="Date the service was rendered (YYYY-MM-DD)")
    date_of_admission: Optional[str] = Field(default=None, description="Admission date (YYYY-MM-DD)")
    date_of_discharge: Optional[str] = Field(default=None, description="Discharge date (YYYY-MM-DD)")


class ClaimCreate(ClaimBase):
    """Schema used when creating a new claim (client → server)."""
    pass


class ClaimInDB(ClaimBase):
    """Schema representing a claim as stored in MongoDB."""
    id: str = Field(default_factory=generate_id, alias="_id", description="Unique claim ID")
    status: ClaimStatus = Field(default=ClaimStatus.PENDING, description="Current claim status")
    risk_score: float = Field(default=0.0, ge=0, le=100, description="Fraud risk score (0-100)")
    risk_flags: list[str] = Field(default_factory=list, description="List of flagged risk indicators")
    document_ids: list[str] = Field(default_factory=list, description="Associated document IDs")
    extraction_confidence: Optional[float] = Field(default=None, ge=0, le=1, description="AI extraction confidence (0-1)")
    created_at: datetime = Field(default_factory=utc_now, description="Record creation timestamp")
    updated_at: datetime = Field(default_factory=utc_now, description="Last update timestamp")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "_id": "a1b2c3d4e5f6",
                "policy_number": "POL-2024-78901",
                "claim_number": "CLM-2024-12345",
                "patient_name": "John Doe",
                "diagnosis": "Acute Appendicitis (K35.80)",
                "treatment_cost": 28500.00,
                "hospital_name": "Metro General Hospital",
                "status": "pending",
                "risk_score": 25.0,
                "risk_flags": [],
                "document_ids": [],
            }
        },
    }


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
