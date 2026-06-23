"""
IntelliClaim AI - PDF & Image Parsing Utilities

Low-level text extraction from PDF and image files.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_pdf(file_path: str) -> str:
    """Extract text content from a PDF file using PyMuPDF (fitz).

    Iterates over every page in the PDF and concatenates extracted text.

    Args:
        file_path: Absolute or relative path to the PDF file.

    Returns:
        The full extracted text from all pages.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If PDF parsing fails.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        page_count = len(doc)
        text_parts: list[str] = []

        for page_num in range(page_count):
            page = doc.load_page(page_num)
            page_text = page.get_text("text")
            if page_text.strip():
                text_parts.append(page_text)

        doc.close()
        full_text = "\n\n".join(text_parts)
        logger.info("Extracted %d characters from PDF (%d pages): %s", len(full_text), page_count, file_path)
        return full_text

    except ImportError:
        logger.error("PyMuPDF (fitz) is not installed. Install with: pip install PyMuPDF")
        raise RuntimeError("PyMuPDF is not installed")
    except Exception as e:
        logger.error("Failed to parse PDF %s: %s", file_path, str(e))
        raise RuntimeError(f"Failed to parse PDF: {str(e)}")


def parse_image(file_path: str) -> str:
    """Extract text content from an image file using Tesseract OCR.

    Args:
        file_path: Absolute or relative path to the image file.

    Returns:
        The extracted text from the image.

    Raises:
        FileNotFoundError: If the file does not exist.
        RuntimeError: If OCR processing fails.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {file_path}")

    try:
        import pytesseract
        from PIL import Image

        image = Image.open(str(path))
        text = pytesseract.image_to_string(image)
        logger.info("Extracted %d characters from image: %s", len(text), file_path)
        return text

    except ImportError as e:
        logger.error("pytesseract or Pillow is not installed: %s", str(e))
        raise RuntimeError(f"OCR dependency not installed: {str(e)}")
    except Exception as e:
        logger.error("Failed to parse image %s: %s", file_path, str(e))
        raise RuntimeError(f"Failed to parse image: {str(e)}")
