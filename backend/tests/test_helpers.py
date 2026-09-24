"""Tests for general helpers."""

import pytest

from utils.helpers import parse_amount, sanitize_filename


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (28500, 28500.0),
        (28500.5, 28500.5),
        ("28500", 28500.0),
        ("$28,500.00", 28500.0),
        ("28,500 USD", 28500.0),
        ("-12.5", -12.5),
        ("", None),
        ("twelve", None),
        ("12.5.3", None),
        (None, None),
        (True, None),
        (float("inf"), None),
        ([1], None),
    ],
)
def test_parse_amount(value, expected):
    assert parse_amount(value) == expected
