"""
IntelliClaim AI - Documents Router

Endpoints for document upload, listing, retrieval, and deletion.
"""

import logging
import os
import re
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Query
from bson import ObjectId

from db.connection import get_database
from services.storage_service import storage_service as storage
from services.ocr_service import ocr_service as ocr
from utils.helpers import generate_id, utc_now

logger = logging.getLogger("intelliclaim.documents")
router = APIRouter()

_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tiff"}
_MAX_FILENAME_LEN = 100
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _sanitize_filename(filename: str) -> str:
    name = re.sub(r"[^\w\-_\.]", "_", filename)
    ext = os.path.splitext(name)[1].lower()
    stem = name[: _MAX_FILENAME_LEN - len(ext)]
    return stem + ext


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a document, extract text via OCR, and classify it."""
    allowed_types = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/tiff",
    ]
    content_type = file.content_type or ""
    if content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {content_type}")

    # Validate file extension matches declared content-type
    original_filename = file.filename or "upload"
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file extension: {ext}")

    # Validate file size
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 50 MB)")
    await file.seek(0)

    # Sanitize filename to prevent path disclosure in errors
    safe_filename = _sanitize_filename(original_filename)

    try:
        db = get_database()

        # Determine file type
        if "pdf" in content_type:
            file_type = "pdf"
        else:
            file_type = "image"

        # Save file
        try:
            file_path = await storage.save_file(file, subdir="documents")
        except Exception as e:
            logger.error("File save failed: %s", e)
            raise HTTPException(status_code=400, detail="Invalid file or filename")
        file_size = file.size or 0

        doc_id = generate_id()

        # Create initial document record
        doc_record = {
            "_id": doc_id,
            "filename": safe_filename,
            "file_type": file_type,
            "file_size": file_size,
            "storage_path": file_path,
            "document_class": "other",
            "extracted_text": None,
            "claim_id": None,
            "processing_status": "processing",
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        await db.documents.insert_one(doc_record)

        # Extract text
        try:
            extracted_text = await ocr.extract_text(file_path, file_type)
        except Exception as e:
            logger.warning("OCR extraction failed: %s", e)
            extracted_text = ""

        # Classify document
        try:
            document_class = await ocr.classify_document(extracted_text)
        except Exception as e:
            logger.warning("Classification failed: %s", e)
            document_class = "other"

        # Update document record
        await db.documents.update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "extracted_text": extracted_text,
                    "document_class": document_class,
                    "processing_status": "processed",
                    "updated_at": utc_now(),
                }
            },
        )

        logger.info("Document uploaded: %s -> %s", safe_filename, document_class)
        return {
            "id": doc_id,
            "filename": safe_filename,
            "file_type": file_type,
            "document_class": document_class,
            "processing_status": "processed",
            "extracted_text_preview": extracted_text[:500] if extracted_text else "",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upload failed: %s", e)
        raise HTTPException(status_code=500, detail="Upload failed")


@router.get("/documents")
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    document_class: Optional[str] = None,
):
    """List all documents with optional filtering."""
    db = get_database()
    query = {}
    if document_class:
        query["document_class"] = document_class

    cursor = db.documents.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(length=limit)
    total = await db.documents.count_documents(query)

    for doc in docs:
        doc["id"] = doc.pop("_id")
        # Truncate extracted text for list view
        if doc.get("extracted_text"):
            doc["extracted_text_preview"] = doc["extracted_text"][:200]
            del doc["extracted_text"]

    return {"documents": docs, "total": total, "skip": skip, "limit": limit}


@router.get("/documents/{document_id}")
async def get_document(document_id: str):
    """Get a single document by ID."""
    db = get_database()
    doc = await db.documents.find_one({"_id": document_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    doc["id"] = doc.pop("_id")
    return doc


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """Delete a document and its stored file."""
    db = get_database()
    doc = await db.documents.find_one({"_id": document_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove file from storage
    try:
        await storage.delete_file(doc["storage_path"])
    except Exception as e:
        logger.warning("Failed to delete file: %s", e)

    await db.documents.delete_one({"_id": document_id})
    return {"message": "Document deleted", "id": document_id}
