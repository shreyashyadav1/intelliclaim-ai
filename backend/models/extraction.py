"""
IntelliClaim AI - Extraction Schema

The eleven claim fields the extractor may produce. Model output is validated
against ExtractedClaimFields before anything is stored: unknown keys (for
example _id or status) are dropped, values are coerced to the expected types,
and anything that cannot be coerced becomes None.
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from utils.helpers import parse_amount

CLAIM_FIELDS: tuple[str, ...] = (
    "policy_number",
    "claim_number",
    "patient_name",
    "diagnosis",
    "treatment_cost",
    "hospital_name",
    "hospital_address",
    "provider_id",
    "date_of_service",
    "date_of_admission",
    "date_of_discharge",
)
DATE_FIELDS: tuple[str, ...] = ("date_of_service", "date_of_admission", "date_of_discharge")
TEXT_FIELDS: tuple[str, ...] = tuple(f for f in CLAIM_FIELDS if f != "treatment_cost" and f not in DATE_FIELDS)

MAX_FIELD_LENGTH = 300

# Values models commonly emit instead of leaving a field out.
_EMPTY_MARKERS = {
    "", "-", "--", "n/a", "na", "none", "null", "nil", "unknown",
    "not available", "not found", "not provided", "not specified",
}
# ISO first, then US-style numeric dates, then spelled-out months.
_DATE_FORMATS = ("%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y")


def clean_text(value: Any) -> str | None:
    """Normalise a model-provided text value; None when empty or not a scalar."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        value = str(value)
    elif isinstance(value, float):
        value = str(int(value)) if value.is_integer() else str(value)
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if text.lower() in _EMPTY_MARKERS:
        return None
    return text[:MAX_FIELD_LENGTH]


def parse_date(value: Any) -> str | None:
    """Return the value as YYYY-MM-DD, or None if it is not a recognisable date."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = clean_text(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class ExtractedClaimFields(BaseModel):
    """Validated extraction output. Only these fields are ever written to a claim."""

    model_config = ConfigDict(extra="ignore")

    policy_number: str | None = None
    claim_number: str | None = None
    patient_name: str | None = None
    diagnosis: str | None = None
    treatment_cost: float | None = None
    hospital_name: str | None = None
    hospital_address: str | None = None
    provider_id: str | None = None
    date_of_service: str | None = None
    date_of_admission: str | None = None
    date_of_discharge: str | None = None

    @field_validator(*TEXT_FIELDS, mode="before")
    @classmethod
    def _coerce_text(cls, value: Any) -> str | None:
        return clean_text(value)

    @field_validator("treatment_cost", mode="before")
    @classmethod
    def _coerce_cost(cls, value: Any) -> float | None:
        amount = parse_amount(value)
        return round(amount, 2) if amount is not None and amount >= 0 else None

    @field_validator(*DATE_FIELDS, mode="before")
    @classmethod
    def _coerce_date(cls, value: Any) -> str | None:
        return parse_date(value)

    def filled_fields(self) -> int:
        """Number of the eleven known fields that have a value."""
        return sum(1 for name in CLAIM_FIELDS if getattr(self, name) is not None)

    def completeness(self) -> float:
        """Share of the eleven known fields that were found, between 0 and 1."""
        return min(round(self.filled_fields() / len(CLAIM_FIELDS), 2), 1.0)
