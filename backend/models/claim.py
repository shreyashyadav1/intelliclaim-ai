"""
IntelliClaim AI - Claim Data Models

Pydantic v2 models for insurance claim data throughout the application lifecycle:
create, read, update, and database representation.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

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


class ClaimUpdate(BaseModel):
    """Schema for partial claim updates (all fields optional)."""
    policy_number: Optional[str] = None
    claim_number: Optional[str] = None
    patient_name: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment_cost: Optional[float] = None
    hospital_name: Optional[str] = None
    hospital_address: Optional[str] = None
    provider_id: Optional[str] = None
    date_of_service: Optional[str] = None
    date_of_admission: Optional[str] = None
    date_of_discharge: Optional[str] = None
    status: Optional[ClaimStatus] = None
    risk_score: Optional[float] = None
    risk_flags: Optional[list[str]] = None
    document_ids: Optional[list[str]] = None
    extraction_confidence: Optional[float] = None
