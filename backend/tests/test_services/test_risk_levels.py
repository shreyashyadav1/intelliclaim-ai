"""Risk bands shared by validation, the claims filter, the flagged-claims list and analytics."""

import pytest

from config import HIGH_RISK_THRESHOLD, Settings, settings
from services.risk_levels import RISK_LEVELS, flagged_claims_query, risk_level, risk_score_condition


def test_default_flag_threshold_is_15():
    assert Settings.model_fields["RISK_FLAG_THRESHOLD"].default == 15.0
    assert HIGH_RISK_THRESHOLD == 60.0


@pytest.mark.parametrize(
    ("score", "level"),
    [(0, "low"), (14.9, "low"), (15, "medium"), (59.9, "medium"), (60, "high"), (100, "high")],
)
def test_levels_at_the_boundaries(monkeypatch, score, level):
    monkeypatch.setattr(settings, "RISK_FLAG_THRESHOLD", 15.0)
    assert risk_level(score) == level


def test_conditions_partition_the_score_range_like_risk_level(monkeypatch):
    monkeypatch.setattr(settings, "RISK_FLAG_THRESHOLD", 15.0)

    def matches(condition: dict[str, float], score: float) -> bool:
        return score >= condition.get("$gte", float("-inf")) and score < condition.get("$lt", float("inf"))

    for score in (0, 5, 14.9, 15, 30, 59.9, 60, 85, 100):
        selected = [level for level in RISK_LEVELS if matches(risk_score_condition(level), score)]
        assert selected == [risk_level(score)], score


def test_flagged_list_is_status_flagged_or_at_least_medium_risk(monkeypatch):
    monkeypatch.setattr(settings, "RISK_FLAG_THRESHOLD", 20.0)
    assert flagged_claims_query() == {"$or": [{"status": "flagged"}, {"risk_score": {"$gte": 20.0}}]}
    assert risk_score_condition("medium") == {"$gte": 20.0, "$lt": HIGH_RISK_THRESHOLD}
