"""
IntelliClaim AI - File Storage Service

Handles saving, retrieving, and deleting uploaded files on the local
filesystem (with structure ready for S3 extension).
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from config import settings
from utils.helpers import generate_id, sanitize_filename

logger = logging.getLogger(__name__)


class StorageService:
    """Local filesystem storage backend for uploaded documents."""

    def __init__(self) -> None:
        self.base_path = Path(settings.LOCAL_STORAGE_PATH)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info("StorageService initialised — base path: %s", self.base_path.resolve())

    async def save_file(self, file: UploadFile, subdir: str = "documents") -> str:
        """Save an uploaded file to the local filesystem.

        Args:
            file: The FastAPI UploadFile object.
            subdir: Subdirectory under the base storage path.

        Returns:
            The relative storage path of the saved file.
        """
        # Build target directory
        target_dir = self.base_path / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Generate a unique filename to avoid collisions
        safe_name = sanitize_filename(file.filename or "unknown")
        unique_name = f"{generate_id()[:12]}_{safe_name}"
        target_path = target_dir / unique_name

        # Stream file to disk
        try:
            content = await file.read()
            with open(target_path, "wb") as f:
                f.write(content)

            relative_path = str(target_path.relative_to(Path(".")))
            logger.info("Saved file: %s (%d bytes)", relative_path, len(content))
            return relative_path

        except Exception as e:
            logger.error("Failed to save file %s: %s", safe_name, str(e))
            raise RuntimeError(f"Failed to save file: {str(e)}")
        finally:
            await file.seek(0)

    async def get_file(self, path: str) -> bytes:
        """Read file contents from the local filesystem.

        Args:
            path: Relative or absolute path to the file.

        Returns:
            The raw file bytes.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(file_path, "rb") as f:
            data = f.read()

        logger.info("Read file: %s (%d bytes)", path, len(data))
        return data

    async def delete_file(self, path: str) -> bool:
        """Delete a file from the local filesystem.

        Args:
            path: Relative or absolute path to the file.

        Returns:
            True if the file was deleted, False if it didn't exist.
        """
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("Attempted to delete non-existent file: %s", path)
            return False

        try:
            file_path.unlink()
            logger.info("Deleted file: %s", path)
            return True
        except Exception as e:
            logger.error("Failed to delete file %s: %s", path, str(e))
            return False

    def get_file_size(self, path: str) -> int:
        """Get the size of a file in bytes.

        Args:
            path: Path to the file.

        Returns:
            File size in bytes, or 0 if file not found.
        """
        file_path = Path(path)
        if file_path.exists():
            return file_path.stat().st_size
        return 0


# Module-level singleton
storage_service = StorageService()
