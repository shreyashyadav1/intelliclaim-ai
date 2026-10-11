"""Tests for the local file storage service."""

import io

import pytest
from fastapi import UploadFile

from services.storage_service import FileTooLargeError, StorageService


def _upload(content: bytes, name: str = "report.pdf") -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=name)


async def test_absolute_storage_path_is_supported(tmp_path):
    """An absolute LOCAL_STORAGE_PATH used to fail in Path.relative_to(".")."""
    storage = StorageService(tmp_path / "volume")
    stored = await storage.save_upload(_upload(b"%PDF-1.7 data"), max_bytes=1024)

    assert stored.size == len(b"%PDF-1.7 data")
    assert stored.path.startswith(str(tmp_path / "volume" / "documents"))
    assert stored.path.endswith("_report.pdf")
    assert await storage.delete_file(stored.path) is True


async def test_relative_storage_path_is_kept_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    storage = StorageService("./uploads")
    stored = await storage.save_upload(_upload(b"data"), max_bytes=1024)

    assert stored.path.startswith("uploads/documents/")
    assert (tmp_path / stored.path).exists()


async def test_oversized_upload_is_removed(tmp_path):
    storage = StorageService(tmp_path)
    with pytest.raises(FileTooLargeError):
        await storage.save_upload(_upload(b"x" * 5000), max_bytes=4096)
    assert list((tmp_path / "documents").iterdir()) == []


async def test_filenames_are_sanitised(tmp_path):
    storage = StorageService(tmp_path)
    stored = await storage.save_upload(_upload(b"data", name="../../etc/passwd"), max_bytes=1024)
    assert stored.path.startswith(str(tmp_path / "documents"))
    assert stored.path.endswith("_passwd")


async def test_files_outside_the_storage_directory_are_not_deleted(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("keep me")
    storage = StorageService(tmp_path / "uploads")

    assert await storage.delete_file(str(outside)) is False
    assert await storage.delete_file(str(tmp_path / "uploads" / ".." / "outside.txt")) is False
    assert outside.exists()


async def test_deleting_a_missing_file_is_not_an_error(tmp_path):
    storage = StorageService(tmp_path)
    assert await storage.delete_file(str(tmp_path / "documents" / "gone.pdf")) is False
