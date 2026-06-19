"""
IntelliClaim AI - Helper Utilities

General-purpose helper functions used across the application.
"""

import uuid
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def generate_id() -> str:
    """Generate a unique identifier string.

    Returns:
        A UUID4 hex string (32 characters, no dashes).
    """
    return uuid.uuid4().hex


def format_currency(amount: float) -> str:
    """Format a numeric amount as a USD currency string.

    Args:
        amount: The numeric value to format.

    Returns:
        A formatted string like '$12,345.67'.
    """
    return f"${amount:,.2f}"


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing potentially dangerous characters.

    Preserves alphanumeric characters, hyphens, underscores, and periods.
    Strips leading/trailing whitespace and dots.

    Args:
        filename: The raw filename to sanitize.

    Returns:
        A sanitized filename safe for filesystem usage.
    """
    # Remove any path separators
    filename = filename.replace("/", "_").replace("\\", "_")
    # Keep only safe characters
    filename = re.sub(r"[^\w\-.]", "_", filename)
    # Remove leading/trailing dots and whitespace
    filename = filename.strip(". ")
    # Collapse multiple underscores
    filename = re.sub(r"_+", "_", filename)
    # If filename is empty after sanitizing, give it a default
    if not filename:
        filename = f"file_{generate_id()[:8]}"
    return filename


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware).

    Returns:
        A timezone-aware datetime object in UTC.
    """
    return datetime.now(timezone.utc)


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert a value to float.

    Args:
        value: The value to convert.
        default: Fallback value if conversion fails.

    Returns:
        The float value, or the default on failure.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to a maximum length, appending ellipsis if truncated.

    Args:
        text: The text to truncate.
        max_length: Maximum allowed character count.

    Returns:
        The truncated text.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0] + "..."
