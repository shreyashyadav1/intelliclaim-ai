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
