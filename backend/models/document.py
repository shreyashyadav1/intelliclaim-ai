"""
IntelliClaim AI - Document Data Models

Pydantic v2 models for uploaded documents: medical reports, invoices,
claim forms, and discharge summaries.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from utils.helpers import generate_id, utc_now


class DocumentClass(str, Enum):
    """Classification of the uploaded document."""
    MEDICAL_REPORT = "medical_report"
    INVOICE = "invoice"
    CLAIM_FORM = "claim_form"
    DISCHARGE_SUMMARY = "discharge_summary"
    OTHER = "other"


class ProcessingStatus(str, Enum):
    """Processing pipeline status of a document."""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class DocumentBase(BaseModel):
    """Core fields shared across all document representations."""
    filename: str = Field(..., min_length=1, description="Original uploaded filename")
    file_type: str = Field(..., description="File type: pdf, image, or other")
    file_size: int = Field(..., ge=0, description="File size in bytes")


class DocumentInDB(DocumentBase):
    """Schema representing a document as stored in MongoDB."""
    id: str = Field(default_factory=generate_id, alias="_id", description="Unique document ID")
    storage_path: str = Field(..., description="Path to the stored file on disk or in S3")
    document_class: DocumentClass = Field(default=DocumentClass.OTHER, description="AI-classified document type")
    extracted_text: Optional[str] = Field(default=None, description="OCR-extracted text content")
    claim_id: Optional[str] = Field(default=None, description="Associated claim ID")
    processing_status: ProcessingStatus = Field(
        default=ProcessingStatus.UPLOADED,
        description="Current processing pipeline status",
    )
    created_at: datetime = Field(default_factory=utc_now, description="Upload timestamp")
    updated_at: datetime = Field(default_factory=utc_now, description="Last update timestamp")

    model_config = {
        "populate_by_name": True,
        "json_schema_extra": {
            "example": {
                "_id": "d1e2f3a4b5c6",
                "filename": "medical_report_john_doe.pdf",
                "file_type": "pdf",
                "file_size": 245760,
                "storage_path": "./uploads/documents/medical_report_john_doe.pdf",
                "document_class": "medical_report",
                "processing_status": "processed",
            }
        },
    }


class DocumentUploadResponse(BaseModel):
    """Response schema returned after a successful document upload."""
    id: str = Field(..., description="Assigned document ID")
    filename: str = Field(..., description="Original filename")
    document_class: DocumentClass = Field(..., description="AI-classified document type")
    processing_status: ProcessingStatus = Field(..., description="Current processing status")
