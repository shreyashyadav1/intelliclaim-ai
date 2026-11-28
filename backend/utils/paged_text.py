"""
IntelliClaim AI - Page-aware document text

Extracted text is stored as one string, with pages joined by a blank line,
plus the offset at which each page starts. Later steps such as search
indexing use the offsets to tell which page a passage came from.
"""

from collections.abc import Sequence
from dataclasses import dataclass

PAGE_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class PagedText:
    """Document text with page boundaries.

    page_starts[i] is the offset in text where page i + 1 begins. A page
    without text has an empty span, so there is one offset per page.
    """

    text: str
    page_starts: tuple[int, ...]

    @classmethod
    def from_pages(cls, pages: Sequence[str]) -> "PagedText":
        """Join page texts with PAGE_SEPARATOR, skipping blank pages in the text."""
        text = ""
        starts: list[int] = []
        for page in pages:
            page = page.strip()
            if page and text:
                text += PAGE_SEPARATOR
            starts.append(len(text))
            text += page
        return cls(text=text, page_starts=tuple(starts))


def valid_page_starts(text: str, page_starts: object) -> bool:
    """Whether page_starts are usable offsets into text (they come from the database)."""
    if not isinstance(page_starts, list | tuple) or not page_starts:
        return False
    if not all(isinstance(start, int) and not isinstance(start, bool) for start in page_starts):
        return False
    if page_starts[0] != 0 or page_starts[-1] > len(text):
        return False
    return all(earlier <= later for earlier, later in zip(page_starts, page_starts[1:], strict=False))


def split_pages(text: str, page_starts: object) -> list[tuple[int | None, str]]:
    """Return (page number, page text) for every page that has text.

    Without valid offsets the whole text is returned as one part whose page
    number is None (unknown).
    """
    if not valid_page_starts(text, page_starts):
        stripped = text.strip()
        return [(None, stripped)] if stripped else []

    bounds = [*page_starts, len(text)]  # type: ignore[misc]
    parts: list[tuple[int | None, str]] = []
    for number, (start, end) in enumerate(zip(bounds, bounds[1:], strict=False), start=1):
        page_text = text[start:end].strip()
        if page_text:
            parts.append((number, page_text))
    return parts
