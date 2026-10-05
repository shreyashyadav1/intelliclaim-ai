"""
IntelliClaim AI - Upload type detection

Uploads are identified by their leading bytes, never by the client-supplied
MIME type, and the file extension must agree with the detected type.
"""

PDF = "pdf"
PNG = "png"
JPEG = "jpeg"
TIFF = "tiff"

SNIFF_BYTES = 1024

EXTENSION_KINDS = {
    ".pdf": PDF,
    ".png": PNG,
    ".jpg": JPEG,
    ".jpeg": JPEG,
    ".tif": TIFF,
    ".tiff": TIFF,
}


def sniff_file_type(head: bytes) -> str | None:
    """Return the file kind for the first bytes of a file, or None if unsupported."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return TIFF
    # PDF readers accept the header anywhere in the first kilobyte.
    if b"%PDF-" in head[:SNIFF_BYTES]:
        return PDF
    return None
