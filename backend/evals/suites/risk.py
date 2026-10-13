"""
Risk suite (no API key needed; needs MongoDB for the duplicate check).

Loads the synthetic claim history and the labelled incoming claims into a
throwaway MongoDB database, runs the application's ValidationService on
every incoming claim with the AI review switched off, and scores the
rule-based risk score against the labels (anomalous or clean):

- PR-AUC (average precision) and ROC-AUC of the continuous score;
- precision/recall/F1 at a grid of score thresholds and at the configured
  RISK_FLAG_THRESHOLD (the flagged-claims list and medium risk; "high" risk
  starts at 60);
- the threshold that maximises F1, searched over every observed score with
  ties going to the higher threshold. RISK_FLAG_THRESHOLD's default (15) was
  chosen by this rule;
- per anomaly variant, the share of claims where the matching rule fired.

With --llm and GROQ_API_KEY set, the same claims are scored again with the
AI review included (one Groq request per claim; --limit caps the count).
"""

import os
from collections import defaultdict
from typing import Any

from config import HIGH_RISK_THRESHOLD, settings
from evals.common import Context, skipped
from evals.config import eval_settings
from evals.metrics import at_threshold, average_precision, best_f1_threshold, roc_auc

NAME = "risk"
THRESHOLDS = (5, 10, 15, 20, 25, 30, 40, 50, 60)
RULE_FLAGS = {
    "duplicate": {"duplicate_claim"},
    "cost_outlier": {"high_cost", "very_high_cost", "zero_cost", "invalid_cost"},
    "date_inconsistency": {"invalid_dates", "long_stay", "date_format"},
    "missing_fields": {"missing_fields"},
}


def _mongo_uri() -> str:
    return eval_settings.MONGODB_URI or os.environ.get("TEST_MONGODB_URI") or "mongodb://localhost:27017"


def _score_metrics(labels: list[bool], scores: list[float]) -> dict[str, Any]:
    thresholds = sorted({*THRESHOLDS, settings.RISK_FLAG_THRESHOLD})
    return {
        "pr_auc": average_precision(labels, scores),
        "roc_auc": roc_auc(labels, scores),
        "thresholds": {f"{t:g}": at_threshold(labels, scores, t) for t in thresholds},
        "flagged": at_threshold(labels, scores, settings.RISK_FLAG_THRESHOLD),
        "best_f1": best_f1_threshold(labels, scores),
        "mean_score": {
            "anomalous": round(sum(s for y, s in zip(labels, scores, strict=True) if y) / max(sum(labels), 1), 2),
            "clean": round(sum(s for y, s in zip(labels, scores, strict=True) if not y)
                           / max(len(labels) - sum(labels), 1), 2),
        },
    }


async def _validate_all(cases: list[dict[str, Any]], *, with_ai: bool) -> list[dict[str, Any]]:
    from evals.llm_support import with_retries
    from services.llm import LLMError
    from services.validation_service import ValidationService

    validator = ValidationService()
    outcomes = []
    for case in cases:
        try:
            if with_ai:
                result = await with_retries(lambda case=case: validator.validate_claim(dict(case["claim"])))
            else:
                result = await validator.validate_claim(dict(case["claim"]))
        except LLMError as exc:
            outcomes.append({"id": case["id"], "error": exc.detail})
            continue
        outcomes.append({
            "id": case["id"],
            "score": result["risk_score"],
            "level": result["risk_level"],
            "rule_flags": sorted({f["type"] for f in result["flags"] if f["origin"] == "rule"}),
            "ai_status": result["ai_review"]["status"],
        })
    return outcomes


def _evaluate(cases: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [(case, outcome) for case, outcome in zip(cases, outcomes, strict=True) if "score" in outcome]
    labels = [case["anomalous"] for case, _ in scored]
    scores = [outcome["score"] for _, outcome in scored]
    metrics = _score_metrics(labels, scores)

    detected: dict[str, list[bool]] = defaultdict(list)
    for case, outcome in scored:
        for anomaly in case["anomalies"]:
            fired = bool(RULE_FLAGS[anomaly["type"]] & set(outcome["rule_flags"]))
            detected[f"{anomaly['type']}/{anomaly['variant']}"].append(fired)
    metrics["rule_detection_rate"] = {
        key: {"rate": round(sum(values) / len(values), 4), "claims": len(values)}
        for key, values in sorted(detected.items())
    }
    clean = [outcome for case, outcome in scored if not case["anomalous"]]
    metrics["clean_claims_with_any_rule_flag"] = round(sum(1 for o in clean if o["rule_flags"]) / len(clean), 4)
    metrics["claims"] = {"scored": len(scored), "anomalous": sum(labels), "clean": len(labels) - sum(labels),
                         "errors": len(outcomes) - len(scored)}
    return metrics


async def run(ctx: Context) -> dict[str, Any]:
    from motor.motor_asyncio import AsyncIOMotorClient

    import db.connection as db_connection
    from db.connection import redact_mongo_uri
    from evals.llm_support import KEY_MISSING, groq_configured, groq_only, no_llm

    uri = _mongo_uri()
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        return skipped(NAME, f"MongoDB is not reachable at {redact_mongo_uri(uri)} (set EVAL_MONGODB_URI); "
                             "the duplicate check needs a database")

    data = ctx.risk_claims
    cases = data["claims"]
    database_name = f"intelliclaim_eval_{os.getpid()}"
    database = client[database_name]
    previous = db_connection._database
    notes = []
    try:
        await database.claims.insert_many([*data["history"], *(case["claim"] for case in cases)])
        db_connection._database = database
        with no_llm():
            rule_outcomes = await _validate_all(cases, with_ai=False)
        metrics = {"rules": _evaluate(cases, rule_outcomes)}

        if ctx.use_llm and groq_configured():
            subset = cases[: ctx.limit]
            async with groq_only() as recorder:
                ai_outcomes = await _validate_all(subset, with_ai=True)
            from evals.llm_support import usage_summary
            from evals.metrics import latency_summary

            metrics["rules_and_ai"] = {
                **_evaluate(subset, ai_outcomes),
                "latency": latency_summary([call.seconds for call in recorder.calls]),
                "usage": usage_summary(recorder.calls, len(subset)),
            }
        elif ctx.use_llm:
            notes.append(f"AI review not scored: {KEY_MISSING}.")
        else:
            notes.append("AI review not scored (pass --llm with GROQ_API_KEY set to include it).")
    finally:
        db_connection._database = previous
        await client.drop_database(database_name)
        client.close()

    return {
        "suite": NAME,
        "status": "ok",
        "config": {"history_claims": len(data["history"]), "incoming_claims": len(cases),
                   "thresholds": list(THRESHOLDS), "risk_flag_threshold": settings.RISK_FLAG_THRESHOLD,
                   "high_risk_threshold": HIGH_RISK_THRESHOLD},
        "metrics": metrics,
        "notes": notes,
        "details": {"rules": rule_outcomes},
    }


def _section(lines: list[str], title: str, m: dict[str, Any]) -> None:
    claims = m["claims"]
    lines += [
        f"**{title}**: {claims['scored']} claims ({claims['anomalous']} anomalous, {claims['clean']} clean"
        f"{', ' + str(claims['errors']) + ' errors' if claims['errors'] else ''}). "
        f"PR-AUC {m['pr_auc']:.3f}, ROC-AUC {m['roc_auc']:.3f}; mean score anomalous "
        f"{m['mean_score']['anomalous']} vs clean {m['mean_score']['clean']}.",
        "",
        "| Flag when score >= | Precision | Recall | F1 | TP | FP | FN |",
        "|---|---|---|---|---|---|---|",
    ]
    row_notes = {f"{settings.RISK_FLAG_THRESHOLD:g}": " (flagged list, medium risk)",
                 f"{HIGH_RISK_THRESHOLD:g}": " (high risk)"}
    for threshold, row in m["thresholds"].items():
        lines.append(f"| {threshold}{row_notes.get(threshold, '')} | {row['precision']:.3f} | {row['recall']:.3f} "
                     f"| {row['f1']:.3f} | {row['tp']} | {row['fp']} | {row['fn']} |")
    best = m["best_f1"]
    if best is not None:
        lines += ["", f"Highest F1 over every observed score (ties to the higher threshold): score >= "
                      f"{best['threshold']:g}, precision {best['precision']:.3f}, recall {best['recall']:.3f}, "
                      f"F1 {best['f1']:.3f}. Configured RISK_FLAG_THRESHOLD: {settings.RISK_FLAG_THRESHOLD:g}."]
    lines += ["", "Rule detection by injected anomaly:", "", "| Anomaly | Claims | Matching rule fired |",
              "|---|---|---|"]
    for key, row in m["rule_detection_rate"].items():
        lines.append(f"| {key} | {row['claims']} | {row['rate']:.3f} |")
    lines += ["", f"Clean claims with at least one rule flag: {m['clean_claims_with_any_rule_flag']:.3f}.", ""]


def summary(result: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    _section(lines, "Rule-based score (AI review off)", result["metrics"]["rules"])
    if "rules_and_ai" in result["metrics"]:
        _section(lines, "Rules + AI review", result["metrics"]["rules_and_ai"])
    lines += [f"_{note}_" for note in result.get("notes", [])]
    return lines
