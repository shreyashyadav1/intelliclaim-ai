"""
Render the dataset's documents to PDFs (generated on demand, not committed).

- text/<id>.pdf: one page per ground-truth page, drawn line by line in
  Helvetica, so the text layer reads back as the ground truth.
- scanned/<id>.pdf: every page rasterised at 200 dpi, rotated by up to
  1.5 degrees, lightly blurred, given Gaussian noise and stored as a JPEG
  in an image-only PDF, like a flatbed scan. Noise is seeded per document.

A manifest records what the files were rendered from, so they are rebuilt
when the ground truth or the renderer changes.
"""

import hashlib
import io
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf
from PIL import Image, ImageFilter
from PIL import __version__ as pillow_version

from evals.paths import GENERATED_DIR

logger = logging.getLogger(__name__)

RENDER_VERSION = 1
PAGE_WIDTH, PAGE_HEIGHT = 612, 792  # US Letter in points
LEFT, TOP, LEADING, FONT_SIZE = 60, 64, 14, 10
SCAN_DPI = 200
MAX_ROTATION_DEGREES = 1.5
BLUR_RADIUS = 0.6
NOISE_SIGMA = 10.0
JPEG_QUALITY = 70
SCAN_SEED = 20260928

TEXT_DIR = GENERATED_DIR / "text"
SCANNED_DIR = GENERATED_DIR / "scanned"
MANIFEST = GENERATED_DIR / "manifest.json"


def _is_heading(line: str, index: int) -> bool:
    return index == 0 or (line.isupper() and len(line) > 3)


def render_text_pdf(pages: list[str], path: Path) -> None:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        for index, line in enumerate(text.split("\n")):
            if line:
                font = "hebo" if _is_heading(line, index) else "helv"
                page.insert_text((LEFT, TOP + index * LEADING), line, fontname=font, fontsize=FONT_SIZE)
    doc.set_metadata({"title": path.stem, "producer": "IntelliClaim evaluation dataset"})
    doc.save(str(path), garbage=3, deflate=True)
    doc.close()


def render_scanned_pdf(text_pdf: Path, path: Path, seed: int) -> None:
    rng = np.random.default_rng(seed)
    source = pymupdf.open(str(text_pdf))
    scan = pymupdf.open()
    for page in source:
        pixmap = page.get_pixmap(dpi=SCAN_DPI, colorspace=pymupdf.csGRAY, alpha=False)
        image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
        angle = float(rng.uniform(-MAX_ROTATION_DEGREES, MAX_ROTATION_DEGREES))
        image = image.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=255)
        image = image.filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))
        noisy = np.asarray(image, dtype=np.float32) + rng.normal(0.0, NOISE_SIGMA, (image.height, image.width))
        image = Image.fromarray(np.clip(noisy, 0, 255).astype(np.uint8), "L")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        target = scan.new_page(width=page.rect.width, height=page.rect.height)
        target.insert_image(target.rect, stream=buffer.getvalue())
    scan.set_metadata({"title": path.stem, "producer": "IntelliClaim evaluation dataset (scanned)"})
    scan.save(str(path), garbage=3, deflate=True)
    scan.close()
    source.close()


def _fingerprint(documents: list[dict[str, Any]]) -> dict[str, Any]:
    pages = json.dumps([[doc["id"], doc["pages"]] for doc in documents], sort_keys=True).encode()
    return {
        "render_version": RENDER_VERSION,
        "pages_sha256": hashlib.sha256(pages).hexdigest(),
        "pymupdf": pymupdf.VersionBind,
        "pillow": pillow_version,
        "numpy": np.__version__,
    }


def ensure_rendered(documents: list[dict[str, Any]], *, scanned: bool = True) -> None:
    """Render any missing or outdated PDFs for the documents."""
    fingerprint = _fingerprint(documents)
    try:
        current = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    except ValueError:
        current = {}
    stale = current.get("fingerprint") != fingerprint
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    SCANNED_DIR.mkdir(parents=True, exist_ok=True)

    rendered = 0
    for index, doc in enumerate(documents):
        text_pdf = TEXT_DIR / doc["filename"]
        if stale or not text_pdf.exists():
            render_text_pdf(doc["pages"], text_pdf)
            rendered += 1
        scan_pdf = SCANNED_DIR / doc["filename"]
        if scanned and (stale or not scan_pdf.exists()):
            render_scanned_pdf(text_pdf, scan_pdf, SCAN_SEED + index)
            rendered += 1
    if stale or rendered:
        MANIFEST.write_text(json.dumps({"fingerprint": fingerprint}, indent=2) + "\n")
    if rendered:
        logger.info("Rendered %d PDF files into %s", rendered, GENERATED_DIR)


def text_pdf_path(doc: dict[str, Any]) -> Path:
    return TEXT_DIR / doc["filename"]


def scanned_pdf_path(doc: dict[str, Any]) -> Path:
    return SCANNED_DIR / doc["filename"]
