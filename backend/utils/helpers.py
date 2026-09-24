"""
IntelliClaim AI - Helper Utilities

General-purpose helper functions used across the application.
"""

import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePath

MAX_FILENAME_LENGTH = 100


def generate_id() -> str:
    """Generate a unique identifier string.

    Returns:
        A UUID4 hex string (32 characters, no dashes).
    """
    return uuid.uuid4().hex


def sanitize_filename(filename: str, max_length: int = MAX_FILENAME_LENGTH) -> str:
    """Sanitize a filename so it is safe to store and display.

    Keeps alphanumerics, hyphens, underscores and periods; drops any directory
    part; strips leading/trailing dots and whitespace; and shortens the stem so
    the result, extension included, fits in max_length characters.

    Args:
        filename: The raw filename to sanitize.
        max_length: Maximum length of the returned name.

    Returns:
        A sanitized filename safe for filesystem usage.
    """
    # Drop any directory component, whichever separator the client used.
    filename = PurePath(filename.replace("\\", "/")).name.strip(". ")
    # Keep only safe characters
    filename = re.sub(r"[^\w\-.]", "_", filename)
    # Remove leading/trailing dots and whitespace
    filename = filename.strip(". ")
    # Collapse multiple underscores
    filename = re.sub(r"_+", "_", filename)
    # If filename is empty after sanitizing, give it a default
    if not filename:
        filename = f"file_{generate_id()[:8]}"

    if len(filename) > max_length:
        stem, dot, extension = filename.rpartition(".")
        if dot and len(extension) < 10:
            filename = stem[: max_length - len(extension) - 1] + "." + extension
        else:
            filename = filename[:max_length]
    return filename


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware).

    Returns:
        A timezone-aware datetime object in UTC.
    """
    return datetime.now(UTC)
