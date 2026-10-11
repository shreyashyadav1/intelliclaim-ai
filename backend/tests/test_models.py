"""Tests for the extraction schema and its coercion helpers."""

from datetime import date, datetime

import pytest

from models.extraction import CLAIM_FIELDS, ExtractedClaimFields, clean_text, parse_date


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  POL-001 ", "POL-001"),
        ("Jane\n  Smith", "Jane Smith"),
        (12345, "12345"),
        (12345.0, "12345"),
        ("N/A", None),
        ("unknown", None),
        ("", None),
        (None, None),
        (True, None),
        (["a"], None),
        ({"a": 1}, None),
    ],
)
def test_clean_text(value, expected):
    assert clean_text(value) == expected


def test_clean_text_truncates_long_values():
    assert len(clean_text("x" * 1000)) == 300


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2024-01-15", "2024-01-15"),
        ("2024-01-15T10:30:00", "2024-01-15"),
        ("2024/01/15", "2024-01-15"),
        ("01/15/2024", "2024-01-15"),
        ("Jan 15, 2024", "2024-01-15"),
        ("15 January 2024", "2024-01-15"),
        (datetime(2024, 1, 15, 9), "2024-01-15"),
        (date(2024, 1, 15), "2024-01-15"),
        ("15/01/2024", None),  # ambiguous day-first dates are not guessed
        ("last week", None),
        (20240115.5, None),
        (None, None),
    ],
)
def test_parse_date(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(28500, 28500.0), ("$28,500.456", 28500.46), ("-10", None), ("free", None), (True, None), (float("nan"), None)],
)
def test_treatment_cost_coercion(value, expected):
    assert ExtractedClaimFields(treatment_cost=value).treatment_cost == expected


def test_unknown_keys_are_dropped():
    fields = ExtractedClaimFields.model_validate({"patient_name": "A", "_id": "x", "status": "approved"})
    assert set(fields.model_dump()) == set(CLAIM_FIELDS)


def test_completeness_is_capped_and_counts_known_fields():
    assert ExtractedClaimFields().completeness() == 0.0
    assert ExtractedClaimFields(patient_name="A").completeness() == 0.09
    full = ExtractedClaimFields.model_validate({name: "2024-01-01" for name in CLAIM_FIELDS} | {"treatment_cost": 1})
    assert full.filled_fields() == 11
    assert full.completeness() == 1.0
