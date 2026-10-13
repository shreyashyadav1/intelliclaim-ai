"""
Normalised matching of model output against ground truth.

Answers (rag-answer suite) are matched by type:
- money: any amount in the answer equals the expected amount (to the cent);
- date: any date in the answer, in ISO, US (MM/DD/YYYY) or spelled-out form;
- number: any integer (digits or a number word up to twenty);
- text: the expected text appears in the answer after case folding and
  dropping spaces, punctuation and the "Dr." title.

Extraction fields have a strict and a lenient comparison. Strict: equality
after normalisation. Lenient (used for precision/recall): identifiers ignore
case and spaces, amounts compare to the cent, names and addresses allow
small formatting differences (rapidfuzz token ratios), and a diagnosis
matches when its ICD-10 code or its description matches.
"""

import re
from datetime import date
from typing import Any

from rapidfuzz import fuzz

from models.extraction import DATE_FIELDS

ID_FIELDS = ("policy_number", "claim_number", "provider_id")

_MONTHS = {
    name: number
    for number, names in enumerate(
        [("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"), ("may",),
         ("june", "jun"), ("july", "jul"), ("august", "aug"), ("september", "sep", "sept"),
         ("october", "oct"), ("november", "nov"), ("december", "dec")],
        start=1,
    )
    for name in names
}
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_NUMBER_WORDS = {
    word: number
    for number, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen twenty".split()
    )
}
_AMOUNT = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?![\d])")
_ICD10 = re.compile(r"\b([A-TV-Z]\d{2}(?:\.[0-9A-Z]{1,4})?)\b")


def normalize_text(value: Any) -> str:
    """Lower-case, punctuation removed (except "/"), whitespace collapsed, "Dr." titles dropped."""
    text = re.sub(r"[^\w/ ]+", " ", str(value).casefold())
    text = re.sub(r"\bdr\b", " ", text)
    return " ".join(text.split())


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", normalize_text(value))


def find_amounts(text: str) -> list[float]:
    amounts = []
    for whole, cents in _AMOUNT.findall(text):
        amounts.append(int(whole.replace(",", "")) + (int(cents.ljust(2, "0")) / 100 if cents else 0))
    return amounts


def _valid_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def find_dates(text: str) -> list[str]:
    """Dates written as YYYY-MM-DD, MM/DD/YYYY, "March 4, 2026" or "4 March 2026", as ISO strings."""
    lowered = text.casefold()
    found = []
    for year, month, day in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lowered):
        found.append(_valid_date(int(year), int(month), int(day)))
    for month, day, year in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", lowered):
        found.append(_valid_date(int(year), int(month), int(day)))
    for month, day, year in re.findall(rf"\b({_MONTH_PATTERN})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b",
                                       lowered):
        found.append(_valid_date(int(year), _MONTHS[month], int(day)))
    for day, month, year in re.findall(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_PATTERN})\.?,?\s+(\d{{4}})\b",
                                       lowered):
        found.append(_valid_date(int(year), _MONTHS[month], int(day)))
    return [value for value in found if value]


def find_numbers(text: str) -> list[int]:
    lowered = text.casefold()
    numbers = [int(value) for value in re.findall(r"\b\d+\b", lowered)]
    numbers += [_NUMBER_WORDS[word] for word in re.findall(r"[a-z]+", lowered) if word in _NUMBER_WORDS]
    return numbers


def answer_matches(expected: str, answer_type: str, answer: str) -> bool:
    """Whether a free-text answer contains the expected answer (see the module docstring)."""
    if answer_type == "money":
        return any(abs(amount - float(expected)) < 0.005 for amount in find_amounts(answer))
    if answer_type == "date":
        return expected in find_dates(answer)
    if answer_type == "number":
        return int(expected) in find_numbers(answer)
    return compact(expected) in compact(answer)


def field_matches(field: str, expected: Any, predicted: Any, *, strict: bool = False) -> bool:
    """Whether an extracted value matches the ground truth (both absent counts as a match)."""
    if expected is None or predicted is None:
        return expected is None and predicted is None
    if field == "treatment_cost":
        try:
            return abs(float(expected) - float(predicted)) < 0.01
        except (TypeError, ValueError):
            return False
    if field in DATE_FIELDS:
        return str(expected) == str(predicted)
    if field in ID_FIELDS:
        return compact(expected) == compact(predicted)

    expected_text, predicted_text = normalize_text(expected), normalize_text(predicted)
    if strict or expected_text == predicted_text:
        return expected_text == predicted_text
    if field == "diagnosis":
        codes = set(_ICD10.findall(str(expected).upper()))
        if codes and codes & set(_ICD10.findall(str(predicted).upper())):
            return True
        description = normalize_text(re.sub(r"\([^)]*\)", " ", str(expected)))
        return fuzz.token_set_ratio(description, predicted_text) >= 90
    if field == "patient_name":
        return fuzz.token_sort_ratio(expected_text, predicted_text) >= 90
    return fuzz.token_set_ratio(expected_text, predicted_text) >= 90
