"""
IntelliClaim AI - OCR Service

Text extraction from PDFs and images (see utils.pdf_parser) and document
classification: OpenAI when OPENAI_API_KEY is set, otherwise keyword
heuristics. Parsing is CPU-bound, so it runs in a worker thread.
"""

import asyncio
import logging

from config import CLASSIFICATION_PARAMS, settings
from services import llm
from services.llm import LLMError
from utils.pdf_parser import DocumentReadError, count_pages, parse_image, parse_pdf

logger = logging.getLogger(__name__)

DOCUMENT_CLASSES = ("medical_report", "invoice", "claim_form", "discharge_summary", "other")

# Keywords used for rule-based document classification fallback
_CLASSIFICATION_KEYWORDS: dict[str, list[str]] = {
    "medical_report": [
        "medical report", "clinical report", "diagnostic report", "lab report",
        "pathology", "radiology", "mri", "ct scan", "blood test", "examination",
        "findings", "physician", "medical history", "prognosis",
    ],
    "invoice": [
        "invoice", "bill", "amount due", "total charges", "payment",
        "billing", "itemized", "charges", "subtotal", "tax", "receipt",
    ],
    "claim_form": [
        "claim form", "insurance claim", "claim number", "policy number",
        "claimant", "policyholder", "coverage", "reimbursement", "authorization",
    ],
    "discharge_summary": [
        "discharge summary", "discharged", "discharge date", "admission date",
        "hospital stay", "discharge instructions", "follow-up", "admitted",
        "inpatient", "length of stay",
    ],
}


class OCRService:
    """Service for extracting text from files and classifying documents."""

    async def count_pages(self, file_path: str, kind: str) -> int:
        """Pages (PDF) or frames (TIFF) in a stored upload; raises DocumentReadError."""
        return await asyncio.to_thread(count_pages, file_path, kind)

    async def extract_text(self, file_path: str, file_type: str) -> str:
        """Extract text from a PDF or image file.

        Raises:
            DocumentProcessingError: with a message that is safe to show users.
        """
        if file_type == "pdf":
            return await asyncio.to_thread(parse_pdf, file_path, max_pages=settings.MAX_DOCUMENT_PAGES)
        if file_type == "image":
            return await asyncio.to_thread(parse_image, file_path, max_pages=settings.MAX_DOCUMENT_PAGES)
        raise DocumentReadError("Unsupported file type.")

    async def classify_document(self, text: str) -> str:
        """Classify a document based on its extracted text.

        Uses OpenAI when an API key is set (and MOCK_LLM is off); otherwise,
        or if that call fails, falls back to keyword heuristics.

        Returns:
            One of: medical_report, invoice, claim_form, discharge_summary, other.
        """
        if not text.strip():
            return "other"

        if settings.has_openai_key and not settings.MOCK_LLM:
            try:
                return await self._classify_with_openai(text)
            except LLMError as e:
                logger.warning("OpenAI classification failed, falling back to keywords: %s", e.detail)

        return self._classify_with_keywords(text)

    async def _classify_with_openai(self, text: str) -> str:
        """Classify a document with the configured OpenAI model (first ~3000 characters)."""
        raw = await llm.openai_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a document classifier for an insurance claim processing system. "
                        "Classify the following document into exactly one category. "
                        "Reply with ONLY the category name, nothing else.\n\n"
                        "Categories:\n" + "\n".join(f"- {name}" for name in DOCUMENT_CLASSES)
                    ),
                },
                {"role": "user", "content": f"Classify this document:\n\n{text[:3000]}"},
            ],
            CLASSIFICATION_PARAMS,
        )
        answer = raw.strip().lower()
        classification = answer if answer in DOCUMENT_CLASSES else "other"
        logger.info("OpenAI classified document as: %s", classification)
        return classification

    def _classify_with_keywords(self, text: str) -> str:
        """Classify a document using keyword matching.

        Counts matching keywords for each category and picks the one with
        the highest hit count.

        Args:
            text: Document text.

        Returns:
            The best-matching category, or 'other' if no keywords match.
        """
        text_lower = text.lower()
        scores: dict[str, int] = {}

        for category, keywords in _CLASSIFICATION_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[category] = score

        if not scores:
            return "other"

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        logger.info("Keyword classifier result: %s (score %d)", best, scores[best])
        return best


# Module-level singleton
ocr_service = OCRService()
