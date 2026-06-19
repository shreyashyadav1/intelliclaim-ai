"""
IntelliClaim AI - OCR Service

Handles text extraction from PDFs and images, plus AI-powered document
classification with a keyword-based fallback when no OpenAI key is set.
"""

import logging
import re
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

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

    async def extract_text(self, file_path: str, file_type: str) -> str:
        """Extract text from a PDF or image file.

        Args:
            file_path: Path to the file on disk.
            file_type: One of 'pdf', 'image', or 'other'.

        Returns:
            The extracted text string (may be empty for unsupported types).
        """
        try:
            if file_type == "pdf":
                from utils.pdf_parser import parse_pdf
                return parse_pdf(file_path)

            elif file_type == "image":
                from utils.pdf_parser import parse_image
                return parse_image(file_path)

            else:
                logger.warning("Unsupported file type for OCR: %s", file_type)
                return ""

        except Exception as e:
            logger.error("OCR extraction failed for %s: %s", file_path, str(e))
            # Return empty string rather than crashing — callers handle empty text
            return ""

    async def classify_document(self, text: str) -> str:
        """Classify a document based on its extracted text.

        Uses OpenAI GPT-4o when an API key is available; otherwise falls
        back to keyword-based heuristics.

        Args:
            text: The extracted text content of the document.

        Returns:
            One of: medical_report, invoice, claim_form, discharge_summary, other.
        """
        if not text.strip():
            return "other"

        # Try OpenAI classification first
        if settings.has_openai_key:
            try:
                return await self._classify_with_openai(text)
            except Exception as e:
                logger.warning("OpenAI classification failed, falling back to keywords: %s", str(e))

        # Keyword-based fallback
        return self._classify_with_keywords(text)

    async def _classify_with_openai(self, text: str) -> str:
        """Classify a document using OpenAI GPT-4o.

        Args:
            text: Document text (truncated to ~3000 chars for the prompt).

        Returns:
            The classified document type string.
        """
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        truncated = text[:3000]

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a document classifier for an insurance claim processing system. "
                        "Classify the following document into exactly one category. "
                        "Reply with ONLY the category name, nothing else.\n\n"
                        "Categories:\n"
                        "- medical_report\n"
                        "- invoice\n"
                        "- claim_form\n"
                        "- discharge_summary\n"
                        "- other"
                    ),
                },
                {
                    "role": "user",
                    "content": f"Classify this document:\n\n{truncated}",
                },
            ],
            temperature=0,
            max_tokens=20,
        )

        raw = response.choices[0].message.content.strip().lower()
        valid = {"medical_report", "invoice", "claim_form", "discharge_summary", "other"}
        classification = raw if raw in valid else "other"
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
