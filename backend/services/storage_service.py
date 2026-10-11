"""
IntelliClaim AI - File Storage Service

Saves uploaded files under LOCAL_STORAGE_PATH, which may be relative to the
working directory or absolute (e.g. a mounted volume).
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from fastapi import UploadFile

from config import settings
from utils.helpers import generate_id, sanitize_filename

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024


class FileTooLargeError(Exception):
    """The upload is larger than the allowed maximum."""

    def __init__(self, limit_bytes: int) -> None:
        self.limit_bytes = limit_bytes
        super().__init__(f"File exceeds {limit_bytes} bytes")


@dataclass(frozen=True)
class StoredFile:
    path: str
    size: int


def _copy_limited(source: BinaryIO, target: Path, max_bytes: int) -> int:
    """Copy source to target in chunks, stopping as soon as max_bytes is exceeded."""
    size = 0
    with open(target, "wb") as out:
        while chunk := source.read(_CHUNK_SIZE):
            size += len(chunk)
            if size > max_bytes:
                raise FileTooLargeError(max_bytes)
            out.write(chunk)
    return size


class StorageService:
    """Local filesystem storage backend for uploaded documents."""

    def __init__(self, base_path: str | Path | None = None) -> None:
        self.base_path = Path(settings.LOCAL_STORAGE_PATH if base_path is None else base_path).expanduser()

    async def save_upload(self, file: UploadFile, *, max_bytes: int, subdir: str = "documents") -> StoredFile:
        """Stream an upload to disk, enforcing max_bytes while copying.

        Raises:
            FileTooLargeError: the file is larger than max_bytes (nothing is kept on disk).
        """
        target_dir = self.base_path / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        # A unique prefix avoids collisions between uploads with the same name.
        target = target_dir / f"{generate_id()[:12]}_{sanitize_filename(file.filename or 'upload')}"

        await file.seek(0)
        try:
            size = await asyncio.to_thread(_copy_limited, file.file, target, max_bytes)
        except BaseException:
            target.unlink(missing_ok=True)
            raise

        logger.info("Saved file: %s (%d bytes)", target, size)
        return StoredFile(path=str(target), size=size)

    async def delete_file(self, path: str) -> bool:
        """Delete a stored file. Paths outside the storage directory are refused.

        Returns:
            True if the file was deleted, False otherwise.
        """
        file_path = Path(path).expanduser()
        if not file_path.resolve().is_relative_to(self.base_path.resolve()):
            logger.warning("Refusing to delete a file outside the storage directory: %s", path)
            return False
        if not file_path.exists():
            logger.warning("Attempted to delete non-existent file: %s", path)
            return False

        try:
            file_path.unlink()
            logger.info("Deleted file: %s", path)
            return True
        except OSError as e:
            logger.error("Failed to delete file %s: %s", path, str(e))
            return False


# Module-level singleton
storage_service = StorageService()
