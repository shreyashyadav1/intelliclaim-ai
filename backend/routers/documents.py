"""
IntelliClaim AI - Documents Router

Endpoints for document upload, listing, retrieval, and deletion.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from config import settings
from db.connection import get_database
from services.claim_service import detach_document
from services.ocr_service import ocr_service as ocr
from services.rag_service import rag_service
from services.storage_service import FileTooLargeError
from services.storage_service import storage_service as storage
from utils.file_types import EXTENSION_KINDS, PDF, SNIFF_BYTES, sniff_file_type
from utils.helpers import generate_id, sanitize_filename, utc_now
from utils.pdf_parser import DocumentProcessingError, TooManyPagesError

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

    415 for unsupported or mismatched types, 413 above MAX_UPLOAD_MB, 400 for
    unreadable or encrypted files and more than MAX_DOCUMENT_PAGES pages. If
    no text can be extracted the document is stored with processing_status
    "failed" and an error_message.
    """
    kind = await _detect_kind(file)
    safe_filename = sanitize_filename(file.filename or "upload")
    file_type = "pdf" if kind == PDF else "image"

    try:
        stored = await storage.save_upload(file, max_bytes=settings.max_upload_bytes)
    except FileTooLargeError:
        raise HTTPException(status_code=413, detail=f"File too large (max {settings.MAX_UPLOAD_MB} MB)") from None

    # Structural checks before anything is recorded: unreadable, encrypted or
    # over-long documents are rejected outright.
    try:
        page_count = await ocr.count_pages(stored.path, kind)
        if page_count > settings.MAX_DOCUMENT_PAGES:
            raise TooManyPagesError(page_count, settings.MAX_DOCUMENT_PAGES)
    except DocumentProcessingError as exc:
        await storage.delete_file(stored.path)
        raise HTTPException(status_code=400, detail=str(exc)) from None

    db = get_database()
    doc_id = generate_id()
    now = utc_now()
    doc_record = {
        "_id": doc_id,
        "filename": safe_filename,
        "file_type": file_type,
        "file_size": stored.size,
        "page_count": page_count,
        "storage_path": stored.path,
        "document_class": "other",
        "extracted_text": None,
        "claim_id": None,
        "processing_status": "processing",
        "error_message": None,
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.documents.insert_one(doc_record)
    except Exception:
        await storage.delete_file(stored.path)
        raise

    # Text extraction failures are recorded on the document, not swallowed.
    status, error_message, extracted_text, document_class = "processed", None, "", "other"
    try:
        extracted_text = await ocr.extract_text(stored.path, file_type)
    except DocumentProcessingError as exc:
        status, error_message = "failed", str(exc)
    else:
        if extracted_text.strip():
            document_class = await ocr.classify_document(extracted_text)
        else:
            status, error_message = "failed", "No text could be extracted from this document."

    await db.documents.update_one(
        {"_id": doc_id},
        {
            "$set": {
                "extracted_text": extracted_text,
                "document_class": document_class,
                "processing_status": status,
                "error_message": error_message,
                "updated_at": utc_now(),
            }
        },
    )

    if status == "failed":
        logger.warning("Document %s (%s) failed processing: %s", doc_id, safe_filename, error_message)
    else:
        logger.info("Document uploaded: %s -> %s", safe_filename, document_class)
    return {
        "id": doc_id,
        "filename": safe_filename,
        "file_type": file_type,
        "file_size": stored.size,
        "page_count": page_count,
        "document_class": document_class,
        "processing_status": status,
        "error_message": error_message,
        "extracted_text_preview": extracted_text[:500],
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
    """Delete a document with its search vectors, claim links and stored file."""
    db = get_database()
    doc = await db.documents.find_one({"_id": document_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Vectors first: if the vector store fails, nothing has been deleted yet and
    # the request can simply be retried.
    vectors_removed = await rag_service.delete_document(document_id)
    await db.documents.delete_one({"_id": document_id})
    unlinked_claims = await detach_document(db, document_id)
    await storage.delete_file(doc["storage_path"])

    logger.info(
        "Deleted document %s (%d vectors, unlinked from %d claims)", document_id, vectors_removed, unlinked_claims
    )
    return {
        "message": "Document deleted",
        "id": document_id,
        "vectors_removed": vectors_removed,
        "unlinked_claims": unlinked_claims,
    }
