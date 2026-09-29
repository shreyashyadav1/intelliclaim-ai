"""
IntelliClaim AI - Documents Router

Endpoints for document upload, listing, retrieval, and deletion.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from config import settings
from db.connection import get_database
from services.ocr_service import ocr_service as ocr
from services.storage_service import FileTooLargeError
from services.storage_service import storage_service as storage
from utils.file_types import EXTENSION_KINDS, PDF, SNIFF_BYTES, sniff_file_type
from utils.helpers import generate_id, sanitize_filename, utc_now

logger = logging.getLogger("intelliclaim.documents")
router = APIRouter()

_UNSUPPORTED_TYPE = "Unsupported file type. Upload a PDF, PNG, JPEG or TIFF (.tif/.tiff) file."


async def _detect_kind(file: UploadFile) -> str:
    """Identify the upload from its bytes; the client's Content-Type is not trusted."""
    extension = Path(file.filename or "").suffix.lower()
    expected = EXTENSION_KINDS.get(extension)
    if expected is None:
        raise HTTPException(status_code=415, detail=_UNSUPPORTED_TYPE)

    head = await file.read(SNIFF_BYTES)
    await file.seek(0)
    if not head:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    kind = sniff_file_type(head)
    if kind is None:
        raise HTTPException(status_code=415, detail=_UNSUPPORTED_TYPE)
    if kind != expected:
        raise HTTPException(
            status_code=415,
            detail=f"The file content is {kind.upper()}, which does not match its {extension} extension.",
        )
    return kind


@router.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a document, extract text via OCR, and classify it.

    415 for unsupported or mismatched types, 413 above MAX_UPLOAD_MB.
    """
    kind = await _detect_kind(file)
    safe_filename = sanitize_filename(file.filename or "upload")
    file_type = "pdf" if kind == PDF else "image"

    try:
        stored = await storage.save_upload(file, max_bytes=settings.max_upload_bytes)
    except FileTooLargeError:
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.MAX_UPLOAD_MB} MB)") from None

    db = get_database()
    doc_id = generate_id()
    now = utc_now()
    doc_record = {
        "_id": doc_id,
        "filename": safe_filename,
        "file_type": file_type,
        "file_size": stored.size,
        "storage_path": stored.path,
        "document_class": "other",
        "extracted_text": None,
        "claim_id": None,
        "processing_status": "processing",
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.documents.insert_one(doc_record)
    except Exception:
        await storage.delete_file(stored.path)
        raise

    # Extract text
    try:
        extracted_text = await ocr.extract_text(stored.path, file_type)
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
        "file_size": stored.size,
        "document_class": document_class,
        "processing_status": "processed",
        "extracted_text_preview": extracted_text[:500] if extracted_text else "",
    }


@router.get("/documents")
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    document_class: str | None = None,
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
