"""
IntelliClaim AI - Risk levels

One definition of the risk bands, shared by validation, the claims filter,
the flagged-claims list and analytics, so every view of a score agrees:

- high: score >= HIGH_RISK_THRESHOLD (60); validation also sets the claim's
  status to "flagged".
- medium: score >= settings.RISK_FLAG_THRESHOLD (default 15, the threshold
  with the highest F1 on the risk evaluation; see backend/evals/README.md).
- low: below RISK_FLAG_THRESHOLD.

The flagged-claims list holds every claim at medium or high risk, plus any
claim whose status is "flagged".
"""

from typing import Any

from config import HIGH_RISK_THRESHOLD, settings

RISK_LEVELS = ("low", "medium", "high")


def risk_level(score: float) -> str:
    """The risk level of a composite score (0-100)."""
    if score >= HIGH_RISK_THRESHOLD:
        return "high"
    if score >= settings.RISK_FLAG_THRESHOLD:
        return "medium"
    return "low"


def risk_score_condition(level: str) -> dict[str, float]:
    """MongoDB condition on risk_score that selects the claims at one risk level."""
    flag = settings.RISK_FLAG_THRESHOLD
    conditions = {
        "low": {"$lt": flag},
        "medium": {"$gte": flag, "$lt": HIGH_RISK_THRESHOLD},
        "high": {"$gte": HIGH_RISK_THRESHOLD},
    }
    return conditions[level]


def flagged_claims_query() -> dict[str, Any]:
    """MongoDB query for the flagged-claims list: flagged status or at least medium risk."""
    return {"$or": [{"status": "flagged"}, {"risk_score": {"$gte": settings.RISK_FLAG_THRESHOLD}}]}
