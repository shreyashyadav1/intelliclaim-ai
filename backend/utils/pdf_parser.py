"""
IntelliClaim AI - PDF & Image Text Extraction

PDF pages are read from their text layer. A page with (almost) no text,
which is what scanners produce, is rendered with PyMuPDF and read with
Tesseract. Images, including every page of a multi-page TIFF, go straight
to Tesseract.

Failures raise DocumentProcessingError subclasses whose messages are safe
to show to API clients; the technical cause is logged.
"""

import functools
import logging

import pymupdf
import pytesseract
from PIL import Image, ImageSequence, UnidentifiedImageError

from utils.file_types import PDF

logger = logging.getLogger(__name__)

OCR_DPI = 300
MAX_OCR_SIDE_PX = 5000  # bounds memory for pages or images with huge dimensions
MIN_TEXT_LAYER_CHARS = 20  # pages with less extractable text than this are OCR'd
TESSERACT_TIMEOUT_SECONDS = 120


class DocumentProcessingError(Exception):
    """Text could not be extracted. The message is safe to show to API clients."""


class DocumentReadError(DocumentProcessingError):
    """The file is corrupt, encrypted or otherwise unreadable."""


class TooManyPagesError(DocumentProcessingError):
    def __init__(self, pages: int, limit: int) -> None:
        super().__init__(f"The document has {pages} pages; the maximum is {limit}.")


class OCRUnavailableError(DocumentProcessingError):
    """Tesseract is not installed on the server."""


class OCRFailedError(DocumentProcessingError):
    """Tesseract ran but failed or timed out."""


@functools.cache
def tesseract_available() -> bool:
    """Whether the tesseract binary can be run (checked once per process)."""
    try:
        pytesseract.get_tesseract_version()
    except Exception:  # TesseractNotFoundError or a broken installation
        logger.warning("Tesseract is not installed; scanned pages and images cannot be read")
        return False
    return True


def _open_pdf(file_path: str) -> pymupdf.Document:
    try:
        doc = pymupdf.open(file_path)
    except (RuntimeError, ValueError) as exc:  # pymupdf.FileDataError is a RuntimeError
        logger.warning("Could not open PDF %s: %s", file_path, exc)
        raise DocumentReadError("The file could not be read as a PDF.") from exc
    if doc.needs_pass:
        doc.close()
        raise DocumentReadError("Password-protected PDFs are not supported.")
    return doc


def _open_image(file_path: str) -> Image.Image:
    try:
        return Image.open(file_path)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        logger.warning("Could not open image %s: %s", file_path, exc)
        raise DocumentReadError("The image could not be read.") from exc


def count_pages(file_path: str, kind: str) -> int:
    """Pages in a PDF, or frames in an image (multi-page TIFFs have several)."""
    if kind == PDF:
        with _open_pdf(file_path) as doc:
            return doc.page_count
    with _open_image(file_path) as image:
        return getattr(image, "n_frames", 1)


def _ocr(image: Image.Image) -> str:
    try:
        return pytesseract.image_to_string(image, timeout=TESSERACT_TIMEOUT_SECONDS)
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRUnavailableError("OCR is not available on the server.") from exc
    except (pytesseract.TesseractError, RuntimeError) as exc:  # pytesseract signals timeouts with RuntimeError
        logger.warning("Tesseract failed: %s", exc)
        raise OCRFailedError("OCR failed while reading the document.") from exc


def _render_page(page: pymupdf.Page) -> Image.Image:
    """Render a PDF page to a grayscale image at OCR_DPI, capped at MAX_OCR_SIDE_PX."""
    zoom = OCR_DPI / 72
    longest_side = max(page.rect.width, page.rect.height) * zoom
    if longest_side > MAX_OCR_SIDE_PX:
        zoom *= MAX_OCR_SIDE_PX / longest_side
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False)
    return Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)


def parse_pdf(file_path: str, *, max_pages: int) -> str:
    """Extract text from every page, falling back to OCR for pages without a text layer.

    Raises:
        DocumentReadError, TooManyPagesError, OCRUnavailableError, OCRFailedError
    """
    parts: list[str] = []
    unread_pages: list[int] = []
    ocr_pages = 0

    with _open_pdf(file_path) as doc:
        if doc.page_count > max_pages:
            raise TooManyPagesError(doc.page_count, max_pages)

        for number, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if len(text) < MIN_TEXT_LAYER_CHARS:
                if tesseract_available():
                    ocr_text = _ocr(_render_page(page)).strip()
                    ocr_pages += 1
                    if len(ocr_text) > len(text):
                        text = ocr_text
                else:
                    unread_pages.append(number)
            if text:
                parts.append(text)
        page_count = doc.page_count

    if unread_pages:
        logger.warning("PDF %s: pages %s have no text layer and OCR is unavailable", file_path, unread_pages)
        if not parts:
            raise OCRUnavailableError(
                "This PDF has no text layer (it looks scanned) and OCR is not available on the server."
            )

    full_text = "\n\n".join(parts)
    logger.info(
        "Extracted %d characters from PDF (%d pages, %d via OCR): %s", len(full_text), page_count, ocr_pages, file_path
    )
    return full_text


def parse_image(file_path: str, *, max_pages: int) -> str:
    """OCR an image; every frame of a multi-page TIFF is read.

    Raises:
        DocumentReadError, TooManyPagesError, OCRUnavailableError, OCRFailedError
    """
    if not tesseract_available():
        raise OCRUnavailableError("Images are read with OCR, which is not available on the server.")

    parts: list[str] = []
    with _open_image(file_path) as image:
        frames = getattr(image, "n_frames", 1)
        if frames > max_pages:
            raise TooManyPagesError(frames, max_pages)
        try:
            for frame in ImageSequence.Iterator(image):
                prepared = frame.convert("L")
                prepared.thumbnail((MAX_OCR_SIDE_PX, MAX_OCR_SIDE_PX))
                text = _ocr(prepared).strip()
                if text:
                    parts.append(text)
        except OSError as exc:  # truncated or corrupt frame data
            logger.warning("Could not decode image %s: %s", file_path, exc)
            raise DocumentReadError("The image could not be read.") from exc

    full_text = "\n\n".join(parts)
    logger.info("Extracted %d characters from image (%d pages): %s", len(full_text), frames, file_path)
    return full_text
