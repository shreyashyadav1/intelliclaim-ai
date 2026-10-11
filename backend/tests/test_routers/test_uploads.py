"""Upload validation: content sniffing, extensions and size limits."""

import io

import pymupdf
import pytest
from PIL import Image

from config import settings


def pdf_bytes(text: str = "Invoice total charges $1,250.00 for patient John Doe.") -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def image_bytes(fmt: str, frames: int = 1) -> bytes:
    images = [Image.new("L", (200, 100), color=255) for _ in range(frames)]
    buffer = io.BytesIO()
    images[0].save(buffer, format=fmt, save_all=frames > 1, append_images=images[1:])
    return buffer.getvalue()


async def _upload(async_client, name: str, content: bytes, content_type: str = "application/octet-stream"):
    return await async_client.post("/api/documents/upload", files={"file": (name, content, content_type)})


async def test_pdf_upload_is_stored_and_recorded(async_client, test_db, storage_dir):
    response = await _upload(async_client, "invoice.pdf", pdf_bytes(), "application/pdf")
    assert response.status_code == 200

    data = response.json()
    assert data["file_type"] == "pdf"
    assert data["file_size"] == len(pdf_bytes())
    assert data["document_class"] == "invoice"
    stored = await test_db.documents.find_one({"_id": data["id"]})
    assert stored["storage_path"].startswith(str(storage_dir))  # absolute LOCAL_STORAGE_PATH works
    assert len(list((storage_dir / "documents").iterdir())) == 1


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("scan.png", image_bytes("PNG")),
        ("scan.jpg", image_bytes("JPEG")),
        ("scan.jpeg", image_bytes("JPEG")),
        ("scan.tif", image_bytes("TIFF")),
        ("scan.TIFF", image_bytes("TIFF")),
    ],
)
async def test_image_uploads_are_accepted(async_client, name, content):
    response = await _upload(async_client, name, content)
    assert response.status_code == 200
    assert response.json()["file_type"] == "image"


async def test_client_content_type_is_ignored(async_client):
    """A PDF labelled image/png is still a PDF; the declared MIME type is not trusted."""
    response = await _upload(async_client, "invoice.pdf", pdf_bytes(), "image/png")
    assert response.status_code == 200
    assert response.json()["file_type"] == "pdf"


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("fake.pdf", image_bytes("PNG")),  # PNG bytes behind a .pdf name
        ("fake.png", pdf_bytes()),
        ("script.pdf", b"#!/bin/sh\necho not a pdf\n"),
        ("animation.gif", b"GIF89a" + b"\x00" * 20),
        ("noextension", pdf_bytes()),
        ("archive.zip", b"PK\x03\x04" + b"\x00" * 20),
    ],
)
async def test_unsupported_or_mismatched_content_is_415(async_client, test_db, storage_dir, name, content):
    response = await _upload(async_client, name, content, "application/pdf")
    assert response.status_code == 415
    assert set(response.json()) == {"detail"}
    assert await test_db.documents.count_documents({}) == 2
    assert not (storage_dir / "documents").exists()


async def test_empty_file_is_400(async_client):
    response = await _upload(async_client, "empty.pdf", b"")
    assert response.status_code == 400
    assert response.json() == {"detail": "Uploaded file is empty"}


async def test_file_over_the_limit_is_413_and_not_kept(async_client, test_db, storage_dir, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    too_big = pdf_bytes() + b"\n%" + b"x" * (1024 * 1024)

    response = await _upload(async_client, "big.pdf", too_big)

    assert response.status_code == 413
    assert response.json() == {"detail": "File too large (max 1 MB)"}
    assert await test_db.documents.count_documents({}) == 2
    assert list((storage_dir / "documents").iterdir()) == []


async def test_declared_content_length_over_the_limit_is_rejected_before_reading(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    response = await async_client.post(
        "/api/documents/upload",
        content=b"x" * (2 * 1024 * 1024),
        headers={"Content-Type": "multipart/form-data; boundary=abc"},
    )
    assert response.status_code == 413


async def test_streamed_body_over_the_limit_is_cut_off(async_client, monkeypatch):
    """Without a Content-Length the body is counted while it streams in."""
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)

    async def _chunks():
        yield (
            b"--abc\r\n"
            b'Content-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
            b"Content-Type: application/pdf\r\n\r\n%PDF-1.7\n"
        )
        for _ in range(40):  # 2.5 MB of file data
            yield b"x" * (64 * 1024)
        yield b"\r\n--abc--\r\n"

    response = await async_client.post(
        "/api/documents/upload",
        content=_chunks(),
        headers={"Content-Type": "multipart/form-data; boundary=abc"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "File too large (max 1 MB)"}


async def test_json_endpoints_have_a_small_body_limit(async_client):
    response = await async_client.post("/api/rag/query", json={"question": "x" * (2 * 1024 * 1024)})
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}


# --- Text extraction outcomes ------------------------------------------------------------------


def scanned_pdf_bytes() -> bytes:
    """A PDF whose only page is an image, like a scanner produces."""
    buffer = io.BytesIO()
    Image.new("L", (800, 1000), color=255).save(buffer, format="PNG")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, stream=buffer.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def no_tesseract(monkeypatch):
    import utils.pdf_parser as pdf_parser

    monkeypatch.setattr(pdf_parser, "tesseract_available", lambda: False)


async def test_text_pdf_is_processed(async_client, test_db):
    data = (await _upload(async_client, "invoice.pdf", pdf_bytes())).json()
    assert data["processing_status"] == "processed"
    assert data["error_message"] is None
    assert data["page_count"] == 1
    assert "John Doe" in data["extracted_text_preview"]


async def test_scanned_pdf_without_ocr_is_recorded_as_failed(async_client, test_db, no_tesseract):
    response = await _upload(async_client, "scan.pdf", scanned_pdf_bytes())
    assert response.status_code == 200

    data = response.json()
    assert data["processing_status"] == "failed"
    assert "no text layer" in data["error_message"]
    stored = await test_db.documents.find_one({"_id": data["id"]})
    assert stored["processing_status"] == "failed"
    assert stored["error_message"] == data["error_message"]

    extract = await async_client.post(f"/api/extract/{data['id']}")
    assert extract.status_code == 400
    assert "Text extraction failed" in extract.json()["detail"]


async def test_image_without_ocr_is_recorded_as_failed(async_client, no_tesseract):
    data = (await _upload(async_client, "scan.tif", image_bytes("TIFF"))).json()
    assert data["processing_status"] == "failed"
    assert "OCR" in data["error_message"]


async def test_document_without_any_text_is_recorded_as_failed(async_client, monkeypatch):
    import utils.pdf_parser as pdf_parser

    monkeypatch.setattr(pdf_parser, "tesseract_available", lambda: True)
    monkeypatch.setattr(pdf_parser, "_ocr", lambda image: "   ")
    data = (await _upload(async_client, "blank.pdf", scanned_pdf_bytes())).json()
    assert data["processing_status"] == "failed"
    assert data["error_message"] == "No text could be extracted from this document."


async def test_too_many_pages_is_400_and_nothing_is_kept(async_client, test_db, storage_dir, monkeypatch):
    monkeypatch.setattr(settings, "MAX_DOCUMENT_PAGES", 2)
    doc = pymupdf.open()
    for number in range(3):
        doc.new_page().insert_text((72, 72), f"Page {number}")
    content = doc.tobytes()
    doc.close()

    response = await _upload(async_client, "long.pdf", content)

    assert response.status_code == 400
    assert response.json() == {"detail": "The document has 3 pages; the maximum is 2."}
    assert await test_db.documents.count_documents({}) == 2
    assert list((storage_dir / "documents").iterdir()) == []


async def test_multi_page_tiff_counts_against_the_page_limit(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_DOCUMENT_PAGES", 2)
    response = await _upload(async_client, "scan.tiff", image_bytes("TIFF", frames=3))
    assert response.status_code == 400


async def test_encrypted_pdf_is_400(async_client):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    content = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()

    response = await _upload(async_client, "locked.pdf", content)
    assert response.status_code == 400
    assert response.json() == {"detail": "Password-protected PDFs are not supported."}


async def test_corrupt_pdf_is_400(async_client):
    response = await _upload(async_client, "broken.pdf", b"%PDF-1.7\nnot actually a pdf")
    assert response.status_code == 400
    assert response.json() == {"detail": "The file could not be read as a PDF."}
