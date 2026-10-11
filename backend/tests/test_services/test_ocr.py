"""
Tests for PDF/image text extraction.

The OCR fallback logic is tested everywhere by patching the Tesseract call.
Tests marked `tesseract` run real OCR and are skipped when the binary is not
installed (CI installs it).
"""

import io
import logging
import shutil

import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

import utils.pdf_parser as pdf_parser
from utils.pdf_parser import (
    DocumentReadError,
    OCRFailedError,
    OCRUnavailableError,
    TooManyPagesError,
    count_pages,
    parse_image,
    parse_pdf,
)

requires_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract is not installed")

SCAN_WORDS = ("INVOICE", "PATIENT", "HOSPITAL")


# --- File builders ------------------------------------------------------------------------


def text_image(lines=SCAN_WORDS) -> Image.Image:
    image = Image.new("L", (1400, 150 * len(lines) + 100), color=255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=72)
    for index, line in enumerate(lines):
        draw.text((60, 60 + index * 150), line, fill=0, font=font)
    return image


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def write_pdf(path, pages) -> str:
    """pages: a list of ("text", str) or ("scan", PIL image) entries."""
    doc = pymupdf.open()
    for kind, content in pages:
        page = doc.new_page()
        if kind == "text":
            page.insert_text((72, 72), content)
        else:
            page.insert_image(page.rect, stream=png_bytes(content))
    doc.save(str(path))
    doc.close()
    return str(path)


def write_tiff(path, images) -> str:
    images[0].save(str(path), format="TIFF", save_all=True, append_images=images[1:])
    return str(path)


@pytest.fixture
def fake_ocr(monkeypatch):
    """Pretend Tesseract is installed and record every image it is asked to read."""
    calls = []

    def _ocr(image):
        calls.append(image.size)
        return f"OCR text from page {len(calls)} with enough characters"

    monkeypatch.setattr(pdf_parser, "tesseract_available", lambda: True)
    monkeypatch.setattr(pdf_parser, "_ocr", _ocr)
    return calls


@pytest.fixture
def no_tesseract(monkeypatch):
    monkeypatch.setattr(pdf_parser, "tesseract_available", lambda: False)


# --- PDFs -------------------------------------------------------------------------------------


def test_text_layer_is_used_without_ocr(tmp_path, fake_ocr):
    path = write_pdf(tmp_path / "a.pdf", [("text", "Invoice for patient John Doe, total charges $1,250.")])
    text = parse_pdf(path, max_pages=50)
    assert "John Doe" in text
    assert fake_ocr == []


def test_scanned_pages_fall_back_to_ocr_page_by_page(tmp_path, fake_ocr):
    path = write_pdf(
        tmp_path / "mixed.pdf",
        [("text", "Page one has a proper text layer with plenty of characters."), ("scan", text_image())],
    )
    text = parse_pdf(path, max_pages=50)

    assert "proper text layer" in text
    assert "OCR text from page 1" in text
    assert len(fake_ocr) == 1  # only the scanned page was rendered


def test_scanned_pages_are_rendered_at_ocr_resolution(tmp_path, fake_ocr):
    parse_pdf(write_pdf(tmp_path / "scan.pdf", [("scan", text_image())]), max_pages=50)
    width, height = fake_ocr[0]
    assert max(width, height) > 2000  # ~300 dpi for a letter/A4 page


def test_huge_pages_are_rendered_within_the_pixel_cap(tmp_path, fake_ocr):
    doc = pymupdf.open()
    doc.new_page(width=14000, height=14000)  # ~194 inches square
    doc.save(str(tmp_path / "huge.pdf"))
    doc.close()

    parse_pdf(str(tmp_path / "huge.pdf"), max_pages=50)

    assert max(fake_ocr[0]) <= pdf_parser.MAX_OCR_SIDE_PX


def test_scanned_pdf_without_tesseract_fails_clearly(tmp_path, no_tesseract):
    path = write_pdf(tmp_path / "scan.pdf", [("scan", text_image())])
    with pytest.raises(OCRUnavailableError, match="no text layer"):
        parse_pdf(path, max_pages=50)


def test_partially_scanned_pdf_without_tesseract_keeps_the_text_pages(tmp_path, no_tesseract, caplog):
    path = write_pdf(
        tmp_path / "mixed.pdf",
        [("text", "Page one has a proper text layer with plenty of characters."), ("scan", text_image())],
    )
    with caplog.at_level(logging.WARNING):
        text = parse_pdf(path, max_pages=50)
    assert "proper text layer" in text
    assert "pages [2]" in caplog.text


def test_page_limit(tmp_path):
    path = write_pdf(tmp_path / "long.pdf", [("text", f"Page {i}") for i in range(4)])
    with pytest.raises(TooManyPagesError, match="4 pages; the maximum is 3"):
        parse_pdf(path, max_pages=3)
    assert count_pages(path, "pdf") == 4


def test_corrupt_pdf_is_a_read_error(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not really a pdf")
    with pytest.raises(DocumentReadError):
        parse_pdf(str(path), max_pages=50)


def test_encrypted_pdf_is_a_read_error(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secret")
    doc.save(str(tmp_path / "locked.pdf"), encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()
    with pytest.raises(DocumentReadError, match="Password-protected"):
        count_pages(str(tmp_path / "locked.pdf"), "pdf")


def test_tesseract_errors_become_ocr_failures(tmp_path, monkeypatch):
    def _broken(image, timeout):
        raise RuntimeError("Tesseract process timeout")

    monkeypatch.setattr(pdf_parser, "tesseract_available", lambda: True)
    monkeypatch.setattr(pdf_parser.pytesseract, "image_to_string", _broken)
    with pytest.raises(OCRFailedError):
        parse_pdf(write_pdf(tmp_path / "scan.pdf", [("scan", text_image())]), max_pages=50)


# --- Images -----------------------------------------------------------------------------------


def test_every_tiff_page_is_read(tmp_path, fake_ocr):
    """Only the first frame of a multi-page TIFF used to be read."""
    path = write_tiff(tmp_path / "scan.tiff", [text_image(), text_image(), text_image()])
    text = parse_image(path, max_pages=50)

    assert len(fake_ocr) == 3
    assert all(f"page {n}" in text for n in (1, 2, 3))
    assert count_pages(path, "tiff") == 3


def test_tiff_page_limit(tmp_path, fake_ocr):
    path = write_tiff(tmp_path / "scan.tiff", [text_image()] * 3)
    with pytest.raises(TooManyPagesError):
        parse_image(path, max_pages=2)
    assert fake_ocr == []


def test_images_without_tesseract_fail_clearly(tmp_path, no_tesseract):
    path = tmp_path / "scan.png"
    path.write_bytes(png_bytes(text_image()))
    with pytest.raises(OCRUnavailableError):
        parse_image(str(path), max_pages=50)


def test_corrupt_image_is_a_read_error(tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    with pytest.raises(DocumentReadError):
        count_pages(str(path), "png")


# --- Real OCR (CI) ---------------------------------------------------------------------------


@pytest.mark.tesseract
@requires_tesseract
def test_real_ocr_reads_a_scanned_pdf(tmp_path):
    pdf_parser.tesseract_available.cache_clear()
    text = parse_pdf(write_pdf(tmp_path / "scan.pdf", [("scan", text_image())]), max_pages=50).upper()
    assert all(word in text for word in SCAN_WORDS)


@pytest.mark.tesseract
@requires_tesseract
def test_real_ocr_reads_every_tiff_page(tmp_path):
    pdf_parser.tesseract_available.cache_clear()
    path = write_tiff(tmp_path / "scan.tiff", [text_image(["INVOICE"]), text_image(["HOSPITAL"])])
    text = parse_image(path, max_pages=50).upper()
    assert "INVOICE" in text
    assert "HOSPITAL" in text
