"""Tests for the evaluation metrics and matching rules."""

import math

import pytest

from evals import matching, metrics


def test_percentile_interpolates_like_numpy():
    assert metrics.percentile([1, 2, 3, 4], 50) == 2.5
    assert metrics.percentile([10], 95) == 10
    assert metrics.percentile([1, 2, 3, 4, 5], 90) == pytest.approx(4.6)
    assert math.isnan(metrics.percentile([], 50))


def test_retrieval_metrics():
    result = metrics.retrieval_metrics([1, 3, None, 2])
    assert result == {"recall@1": 0.25, "recall@3": 0.75, "recall@5": 0.75, "mrr": round((1 + 1 / 3 + 0.5) / 4, 4),
                      "queries": 4}
    assert metrics.first_relevant_rank(["a", "b", "c"], {"c", "b"}) == 2
    assert metrics.first_relevant_rank(["a"], {"z"}) is None


def test_error_rates_ignore_whitespace_layout():
    assert metrics.character_error_rate("Total due:\n$10.00", "Total  due: $10.00") == 0.0
    assert metrics.character_error_rate("abcd", "abed") == 0.25
    assert metrics.word_error_rate("a b c d", "a x c") == 0.5
    assert metrics.character_error_rate("", "") == 0.0


def test_classification_report_counts_and_confusion_matrix():
    labels = ["a", "b", "c"]
    report = metrics.classification_report(["a", "a", "b", "c"], ["a", "b", "b", "b"], labels)
    assert report["accuracy"] == 0.5
    assert report["per_class"]["b"] == {"precision": 0.3333, "recall": 1.0, "f1": 0.5, "support": 1}
    assert report["per_class"]["c"]["recall"] == 0.0
    assert report["confusion_matrix"]["matrix"] == [[1, 1, 0], [0, 1, 0], [0, 1, 0]]
    assert report["macro_f1"] == round((2 / 3 + 0.5 + 0.0) / 3, 4)


def test_average_precision_is_the_stepwise_precision_recall_sum_with_ties_grouped():
    # Thresholds 0.9, 0.8, 0.7 (two tied items), 0.1:
    # recall 1/3 at precision 1, then recall 1 at precision 3/4 -> 1/3 * 1 + 2/3 * 3/4
    assert metrics.average_precision([True, False, True, True, False], [0.9, 0.8, 0.7, 0.7, 0.1]) == 0.8333
    assert metrics.average_precision([True, False], [1.0, 0.0]) == 1.0
    assert metrics.average_precision([False, False], [1.0, 0.0]) == 0.0


def test_roc_auc_counts_ties_as_half():
    assert metrics.roc_auc([True, False], [1, 0]) == 1.0
    assert metrics.roc_auc([True, False], [1, 1]) == 0.5
    assert math.isnan(metrics.roc_auc([True], [1]))


def test_precision_recall_at_a_threshold():
    result = metrics.at_threshold([True, True, False, False], [30, 10, 30, 0], 25)
    assert (result["tp"], result["fp"], result["fn"], result["tn"]) == (1, 1, 1, 1)
    assert result["precision"] == result["recall"] == 0.5


def test_best_f1_threshold_searches_observed_scores_and_breaks_ties_upwards():
    labels = [True, True, True, False, False, False]
    scores = [40, 25, 15, 15, 5, 0]
    best = metrics.best_f1_threshold(labels, scores)
    # >= 5: P 3/5, R 1 (F1 0.75); >= 15: P 3/4, R 1 (F1 0.857); >= 25: P 1, R 2/3 (F1 0.8)
    assert (best["threshold"], best["precision"], best["recall"]) == (15, 0.75, 1.0)

    # >= 10: P 1/2, R 1; >= 20: P 1, R 1/2. Both have F1 2/3, so the higher threshold wins the tie.
    assert metrics.best_f1_threshold([True, True, False, False], [20, 10, 10, 10])["threshold"] == 20
    assert metrics.best_f1_threshold([True, True, False], [15, 5, 0])["threshold"] == 5
    assert metrics.best_f1_threshold([True, False], [0, 0]) is None


def test_field_counts_treat_wrong_values_as_false_positive_and_negative():
    counts = metrics.field_counts([("A", "A", True), ("A", "B", False), (None, "C", False), ("D", None, False),
                                   (None, None, True)])
    assert (counts["tp"], counts["fp"], counts["fn"]) == (1, 2, 2)
    assert counts["precision"] == pytest.approx(1 / 3, abs=1e-4)


# --- Matching -------------------------------------------------------------------------------


def test_amounts_dates_and_numbers_are_found_in_free_text():
    assert matching.find_amounts("The total is $4,512.30 (was 4512.3).") == [4512.30, 4512.30]
    assert matching.find_dates("Discharged on 2026-04-27, seen 03/04/2026, due March 4, 2026 or 4 Mar 2026.") == [
        "2026-04-27", "2026-03-04", "2026-03-04", "2026-03-04",
    ]
    assert matching.find_dates("13/45/2026 is not a date") == []
    assert matching.find_numbers("Stayed three nights (3 days)") == [3, 3]


@pytest.mark.parametrize(
    ("expected", "answer_type", "answer", "matches"),
    [
        ("4512.30", "money", "The total amount due is $4,512.30 [1].", True),
        ("4512.30", "money", "The total amount due is $4,512.00.", False),
        ("2026-04-27", "date", "The patient was discharged on April 27, 2026 [2].", True),
        ("3", "number", "They stayed for three days.", True),
        ("Dr. Michael Meza", "text", "The examining physician was Michael Meza [1].", True),
        ("134/88 mmHg", "text", "Blood pressure was 134/88 mm Hg.", True),
        ("Clopidogrel", "text", "The documents do not say.", False),
    ],
)
def test_answer_matching(expected, answer_type, answer, matches):
    assert matching.answer_matches(expected, answer_type, answer) is matches


@pytest.mark.parametrize(
    ("field", "expected", "predicted", "lenient", "strict"),
    [
        ("policy_number", "POL-2026-22588", "pol-2026-22588", True, True),
        ("treatment_cost", 45195.97, 45195.97, True, True),
        ("treatment_cost", 45195.97, 45195.0, False, False),
        ("date_of_service", "2026-05-08", "2026-05-08", True, True),
        ("diagnosis", "Fracture of right femoral neck (S72.001A)", "S72.001A", True, False),
        ("diagnosis", "Acute appendicitis (K35.80)", "acute appendicitis", True, False),
        ("diagnosis", "Acute appendicitis (K35.80)", "Pneumonia (J18.9)", False, False),
        ("patient_name", "Stephen Marshall", "Marshall, Stephen", True, False),
        ("hospital_address", "0455 Ryan Grove, North Brendaborough, MN 98344",
         "0455 Ryan Grove North Brendaborough MN 98344", True, True),
        ("hospital_name", "Cinderholt Memorial Hospital", None, False, False),
        ("claim_number", None, None, True, True),
    ],
)
def test_field_matching(field, expected, predicted, lenient, strict):
    assert matching.field_matches(field, expected, predicted) is lenient
    assert matching.field_matches(field, expected, predicted, strict=True) is strict
