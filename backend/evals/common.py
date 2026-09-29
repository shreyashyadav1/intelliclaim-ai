"""Run context shared by the suites: dataset access, extracted text and run metadata."""

import json
import logging
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property
from importlib import metadata
from pathlib import Path
from typing import Any

from evals.dataset.documents import document_text
from evals.paths import BACKEND_DIR, DOCUMENTS_FILE, QA_FILE, RISK_CLAIMS_FILE
from utils.paged_text import PagedText

logger = logging.getLogger("evals")

PACKAGES = (
    "fastembed", "chromadb", "llama-index-core", "llama-index-vector-stores-chroma", "langchain-core",
    "langchain-chroma", "langchain-community", "langchain-classic", "langchain-groq", "rank-bm25", "groq",
    "PyMuPDF", "pytesseract", "Pillow", "numpy", "Faker", "RapidFuzz",
)


def skipped(suite: str, reason: str) -> dict[str, Any]:
    logger.warning("%s: skipped - %s", suite, reason)
    return {"suite": suite, "status": "skipped", "reason": reason}


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=BACKEND_DIR, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def environment(argv: list[str]) -> dict[str, Any]:
    """What produced a run: command, commit, interpreter and package versions."""
    from utils.pdf_parser import tesseract_available

    versions = {}
    for package in PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    tesseract = None
    if tesseract_available():
        import pytesseract

        tesseract = str(pytesseract.get_tesseract_version())
    status = _git("status", "--porcelain", "--", ".")
    return {
        "command": "python -m evals.run " + " ".join(argv),
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(status) if status is not None else None,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "tesseract": tesseract,
        "packages": versions,
    }


@dataclass
class Context:
    """Lazily loaded dataset and derived text, shared by the suites of one run."""

    limit: int | None = None
    use_llm: bool = False
    retrieval_mode: str | None = None
    _ocr: dict[str, PagedText] | None = field(default=None, repr=False)
    ocr_seconds: dict[str, float] = field(default_factory=dict)

    @cached_property
    def documents(self) -> list[dict[str, Any]]:
        return json.loads(Path(DOCUMENTS_FILE).read_text())["documents"]

    @cached_property
    def questions(self) -> list[dict[str, Any]]:
        return json.loads(Path(QA_FILE).read_text())["questions"]

    @cached_property
    def risk_claims(self) -> dict[str, Any]:
        return json.loads(Path(RISK_CLAIMS_FILE).read_text())

    @cached_property
    def text_layer(self) -> dict[str, PagedText]:
        """Each document's text as the application reads it from the text PDF."""
        from evals.dataset.render import ensure_rendered, text_pdf_path
        from utils.pdf_parser import read_pdf

        ensure_rendered(self.documents, scanned=False)
        return {doc["id"]: read_pdf(str(text_pdf_path(doc)), max_pages=50) for doc in self.documents}

    def scanned_text(self) -> dict[str, PagedText]:
        """Each document's text as the application OCRs it from the scanned PDF (needs tesseract)."""
        if self._ocr is None:
            from evals.dataset.render import ensure_rendered, scanned_pdf_path
            from utils.pdf_parser import read_pdf

            ensure_rendered(self.documents, scanned=True)
            ocr: dict[str, PagedText] = {}
            for position, doc in enumerate(self.documents, start=1):
                started = time.perf_counter()
                ocr[doc["id"]] = read_pdf(str(scanned_pdf_path(doc)), max_pages=50)
                self.ocr_seconds[doc["id"]] = time.perf_counter() - started
                if position % 10 == 0:
                    logger.info("OCR: %d/%d documents", position, len(self.documents))
            self._ocr = ocr
        return self._ocr


__all__ = ["Context", "document_text", "environment", "skipped"]
