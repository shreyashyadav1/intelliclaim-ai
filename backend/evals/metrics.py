"""Metric functions shared by the suites. Pure functions over plain Python values."""

import math
from collections.abc import Iterable, Sequence
from typing import Any

from rapidfuzz.distance import Levenshtein


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------
def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (numpy's default); q in [0, 100]."""
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * q / 100
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize(values: Sequence[float], digits: int = 4) -> dict[str, float]:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": round(sum(values) / len(values), digits),
        "median": round(percentile(values, 50), digits),
        "p90": round(percentile(values, 90), digits),
        "max": round(max(values), digits),
    }


def latency_summary(seconds: Sequence[float]) -> dict[str, float]:
    """p50/p95/mean in milliseconds."""
    if not seconds:
        return {"n": 0}
    ms = [value * 1000 for value in seconds]
    return {
        "n": len(ms),
        "p50_ms": round(percentile(ms, 50), 1),
        "p95_ms": round(percentile(ms, 95), 1),
        "mean_ms": round(sum(ms) / len(ms), 1),
    }


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def first_relevant_rank(ranked_ids: Sequence[str], relevant: Iterable[str]) -> int | None:
    """1-based rank of the first relevant id, or None when none was retrieved."""
    relevant = set(relevant)
    for rank, item in enumerate(ranked_ids, start=1):
        if item in relevant:
            return rank
    return None


def retrieval_metrics(ranks: Sequence[int | None], ks: Sequence[int] = (1, 3, 5)) -> dict[str, float]:
    """recall@k (share of queries with a relevant result in the top k) and MRR."""
    n = len(ranks)
    if n == 0:
        return {}
    metrics = {f"recall@{k}": round(sum(1 for r in ranks if r is not None and r <= k) / n, 4) for k in ks}
    metrics["mrr"] = round(sum(1 / r for r in ranks if r is not None) / n, 4)
    metrics["queries"] = n
    return metrics


# ---------------------------------------------------------------------------
# Text similarity
# ---------------------------------------------------------------------------
def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein distance / reference length, after collapsing whitespace."""
    reference, hypothesis = normalize_whitespace(reference), normalize_whitespace(hypothesis)
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return Levenshtein.distance(reference, hypothesis) / len(reference)


def word_error_rate(reference: str, hypothesis: str) -> float:
    reference_words, hypothesis_words = reference.split(), hypothesis.split()
    if not reference_words:
        return 0.0 if not hypothesis_words else 1.0
    return Levenshtein.distance(reference_words, hypothesis_words) / len(reference_words)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def classification_report(y_true: Sequence[str], y_pred: Sequence[str], labels: Sequence[str]) -> dict[str, Any]:
    """Accuracy, per-class precision/recall/F1, macro F1 over classes present in y_true, confusion matrix."""
    matrix = [[0] * len(labels) for _ in labels]
    index = {label: i for i, label in enumerate(labels)}
    for truth, prediction in zip(y_true, y_pred, strict=True):
        matrix[index[truth]][index[prediction]] += 1

    per_class = {}
    for label in labels:
        i = index[label]
        tp = matrix[i][i]
        fp = sum(matrix[r][i] for r in range(len(labels))) - tp
        fn = sum(matrix[i]) - tp
        precision, recall, f1 = _prf(tp, fp, fn)
        per_class[label] = {
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4), "support": tp + fn,
        }
    present = [label for label in labels if per_class[label]["support"]]
    correct = sum(matrix[i][i] for i in range(len(labels)))
    return {
        "accuracy": round(correct / len(y_true), 4) if y_true else 0.0,
        "macro_f1": round(sum(per_class[label]["f1"] for label in present) / len(present), 4) if present else 0.0,
        "per_class": per_class,
        "confusion_matrix": {"labels": list(labels), "rows_are": "true class", "matrix": matrix},
    }


# ---------------------------------------------------------------------------
# Binary scoring (risk)
# ---------------------------------------------------------------------------
def at_threshold(labels: Sequence[bool], scores: Sequence[float], threshold: float) -> dict[str, float]:
    """Precision/recall/F1 when score >= threshold means "flag"."""
    tp = sum(1 for y, s in zip(labels, scores, strict=True) if y and s >= threshold)
    fp = sum(1 for y, s in zip(labels, scores, strict=True) if not y and s >= threshold)
    fn = sum(1 for y, s in zip(labels, scores, strict=True) if y and s < threshold)
    tn = len(labels) - tp - fp - fn
    precision, recall, f1 = _prf(tp, fp, fn)
    return {
        "threshold": threshold, "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def best_f1_threshold(labels: Sequence[bool], scores: Sequence[float]) -> dict[str, float] | None:
    """The flag threshold with the highest F1, or None when no score is above zero.

    Candidates are the distinct positive scores: a threshold between two
    observed scores flags the same items as the next observed score, so
    these are the only distinct choices. Ties go to the higher threshold,
    which flags fewer items for the same F1.
    """
    best = None
    for threshold in sorted({score for score in scores if score > 0}):
        row = at_threshold(labels, scores, threshold)
        if best is None or row["f1"] >= best["f1"]:
            best = row
    return best


def average_precision(labels: Sequence[bool], scores: Sequence[float]) -> float:
    """Area under the precision-recall curve as average precision (step-wise, ties grouped).

    Matches sklearn.metrics.average_precision_score: sum over distinct score
    thresholds of (recall_i - recall_{i-1}) * precision_i.
    """
    positives = sum(1 for y in labels if y)
    if positives == 0:
        return 0.0
    pairs = sorted(zip(scores, labels, strict=True), key=lambda pair: -pair[0])
    ap, tp, fp, previous_recall, i = 0.0, 0, 0, 0.0, 0
    while i < len(pairs):
        threshold = pairs[i][0]
        while i < len(pairs) and pairs[i][0] == threshold:
            tp += pairs[i][1]
            fp += not pairs[i][1]
            i += 1
        recall = tp / positives
        ap += (recall - previous_recall) * (tp / (tp + fp))
        previous_recall = recall
    return round(ap, 4)


def roc_auc(labels: Sequence[bool], scores: Sequence[float]) -> float:
    """Probability that a random positive scores above a random negative (ties count half)."""
    positive = [s for y, s in zip(labels, scores, strict=True) if y]
    negative = [s for y, s in zip(labels, scores, strict=True) if not y]
    if not positive or not negative:
        return math.nan
    wins = sum((p > n) + 0.5 * (p == n) for p in positive for n in negative)
    return round(wins / (len(positive) * len(negative)), 4)


# ---------------------------------------------------------------------------
# Field extraction
# ---------------------------------------------------------------------------
def field_counts(pairs: Iterable[tuple[Any, Any, bool]]) -> dict[str, float]:
    """Precision/recall/F1 for one field from (expected, predicted, matches) triples.

    A wrong value counts as both a false positive and a false negative; a
    value where the ground truth has none is a false positive.
    """
    tp = fp = fn = 0
    for expected, predicted, matches in pairs:
        if predicted is not None and expected is not None and matches:
            tp += 1
            continue
        if predicted is not None:
            fp += 1
        if expected is not None:
            fn += 1
    precision, recall, f1 = _prf(tp, fp, fn)
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
            "tp": tp, "fp": fp, "fn": fn}
