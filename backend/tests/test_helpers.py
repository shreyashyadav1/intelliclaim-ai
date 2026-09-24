"""Tests for general helpers."""

import pytest

from utils.helpers import sanitize_filename


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\me\\scan (1).PDF", "scan_1_.PDF"),
        ("   ..hidden.pdf", "hidden.pdf"),
        ("claim form.tiff", "claim_form.tiff"),
        ("résumé.png", "résumé.png"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_keeps_extension_when_truncating():
    name = sanitize_filename("a" * 150 + ".pdf")
    assert len(name) == 100
    assert name.endswith(".pdf")


def test_sanitize_filename_falls_back_to_a_generated_name():
    assert sanitize_filename("").startswith("file_")
    assert sanitize_filename("...").startswith("file_")
