"""
IntelliClaim AI - AI review schema

Validates the JSON an LLM returns when it reviews a claim for risk.
Malformed flags are dropped, numbers are coerced and clamped to their
ranges, and free text is length-limited, so model output can never raise
a TypeError further down the scoring code.
"""

import re
from typing import Any, Literal

from pydantic import BaseModel, ValidationError, field_validator

from utils.helpers import parse_amount

MAX_AI_FLAGS = 20
REVIEW_KEYS = frozenset({"risk_flags", "ai_risk_score", "summary"})

_SEVERITY_ALIASES = {
    "critical": "high",
    "severe": "high",
    "major": "high",
    "moderate": "medium",
    "minor": "low",
    "info": "low",
}
_DEFAULT_CONFIDENCE = 0.5


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _one_line(value: Any, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


class AIRiskFlag(BaseModel):
    type: str = "ai_observation"
    description: str
    severity: Literal["low", "medium", "high"] = "medium"
    confidence: float = _DEFAULT_CONFIDENCE

    @field_validator("type", mode="before")
    @classmethod
    def _normalise_type(cls, value: Any) -> str:
        text = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") if isinstance(value, str) else ""
        return text[:50] or "ai_observation"

    @field_validator("description", mode="before")
    @classmethod
    def _require_description(cls, value: Any) -> str:
        text = _one_line(value, 500)
        if not text:
            raise ValueError("description is required")
        return text

    @field_validator("severity", mode="before")
    @classmethod
    def _normalise_severity(cls, value: Any) -> str:
        if isinstance(value, str):
            severity = value.strip().lower()
            severity = _SEVERITY_ALIASES.get(severity, severity)
            if severity in ("low", "medium", "high"):
                return severity
        return "medium"

    @field_validator("confidence", mode="before")
    @classmethod
    def _normalise_confidence(cls, value: Any) -> float:
        percent = isinstance(value, str) and value.strip().endswith("%")
        number = parse_amount(value.strip().rstrip("%") if isinstance(value, str) else value)
        if number is None:
            return _DEFAULT_CONFIDENCE
        if percent or 1 < number <= 100:
            number /= 100
        return _clamp(number, 0.0, 1.0)


class AIReview(BaseModel):
    risk_flags: list[AIRiskFlag] = []
    ai_risk_score: float = 0.0
    summary: str = ""

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _keep_valid_flags(cls, value: Any) -> list[AIRiskFlag]:
        if not isinstance(value, list):
            return []
        flags = []
        for item in value[:MAX_AI_FLAGS]:
            if isinstance(item, str):
                item = {"description": item}
            if not isinstance(item, dict):
                continue
            try:
                flags.append(AIRiskFlag.model_validate(item))
            except ValidationError:
                continue
        return flags

    @field_validator("ai_risk_score", mode="before")
    @classmethod
    def _clamp_score(cls, value: Any) -> float:
        number = parse_amount(value)
        return _clamp(number, 0.0, 100.0) if number is not None else 0.0

    @field_validator("summary", mode="before")
    @classmethod
    def _clean_summary(cls, value: Any) -> str:
        return _one_line(value, 1000)

    @property
    def average_confidence(self) -> float:
        """Mean confidence of the AI flags; 0 when the review raised no flags."""
        if not self.risk_flags:
            return 0.0
        return round(sum(flag.confidence for flag in self.risk_flags) / len(self.risk_flags), 2)
