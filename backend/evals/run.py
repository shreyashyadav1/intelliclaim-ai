"""
Run evaluation suites (from backend/).

    python -m evals.run --suite retrieval
    python -m evals.run --suite offline --check-thresholds
    python -m evals.run --suite extraction --limit 20

--suite can be repeated; "offline" selects retrieval, ocr, classification
and risk (no API key needed) and "all" adds extraction and rag-answer. Each
run writes results.json and summary.md to evals/results/<UTC timestamp>/
(or --output-dir). With --check-thresholds the exit status is 1 when a
metric in evals/thresholds.json is out of bounds or a suite that has
thresholds did not run.
"""

import argparse
import asyncio
import importlib
import inspect
import json
import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.common import Context, environment
from evals.paths import RESULTS_DIR, THRESHOLDS_FILE

logger = logging.getLogger("evals")

SUITES = {
    "retrieval": "evals.suites.retrieval",
    "ocr": "evals.suites.ocr",
    "classification": "evals.suites.classification",
    "risk": "evals.suites.risk",
    "extraction": "evals.suites.extraction",
    "rag-answer": "evals.suites.rag_answer",
}
OFFLINE = ("retrieval", "ocr", "classification", "risk")
GROUPS = {"offline": OFFLINE, "all": tuple(SUITES)}


def selected_suites(names: list[str]) -> list[str]:
    chosen: list[str] = []
    for name in names:
        for suite in GROUPS.get(name, (name,)):
            if suite not in chosen:
                chosen.append(suite)
    return chosen


async def run_suite(name: str, ctx: Context) -> dict[str, Any]:
    module = importlib.import_module(SUITES[name])
    logger.info("Running %s", name)
    started = time.perf_counter()
    try:
        result = module.run(ctx)
        if inspect.isawaitable(result):
            result = await result
    except Exception as exc:  # a failing suite must not hide the others' results
        logger.exception("%s failed", name)
        result = {"suite": name, "status": "error", "reason": f"{type(exc).__name__}: {exc}"}
    result["duration_seconds"] = round(time.perf_counter() - started, 1)
    return result


def lookup(metrics: dict[str, Any], path: str) -> Any:
    value: Any = metrics
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def check_thresholds(results: dict[str, dict], thresholds: dict[str, dict], suites: list[str]) -> list[str]:
    """Failures for every threshold of a selected suite that is not met."""
    failures = []
    for suite, rules in thresholds.items():
        if suite.startswith("_") or suite not in suites:
            continue
        result = results.get(suite, {})
        if result.get("status") != "ok":
            failures.append(f"{suite}: has thresholds but did not run ({result.get('reason', 'not run')})")
            continue
        for path, rule in rules.items():
            value = lookup(result["metrics"], path)
            if not isinstance(value, int | float):
                failures.append(f"{suite}: metric {path} is missing")
            elif "min" in rule and value < rule["min"]:
                failures.append(f"{suite}: {path} = {value} is below the minimum {rule['min']}")
            elif "max" in rule and value > rule["max"]:
                failures.append(f"{suite}: {path} = {value} is above the maximum {rule['max']}")
    return failures


def write_summary(path: Path, env: dict[str, Any], results: dict[str, dict], failures: list[str] | None) -> None:
    lines = [
        f"# Evaluation run {env['started_at']}",
        "",
        f"- Command: `{env['command']}` (from `backend/`)",
        f"- Commit: `{env['git_commit']}`{' (uncommitted changes)' if env['git_dirty'] else ''}",
        f"- Python {env['python']} on {env['platform']}; tesseract {env['tesseract'] or 'not installed'}",
        "",
    ]
    for name, result in results.items():
        lines += [f"## {name}", ""]
        if result["status"] != "ok":
            lines += [f"**{result['status']}**: {result.get('reason', '')}", ""]
            continue
        module = importlib.import_module(SUITES[name])
        lines += [*module.summary(result), "", f"_Duration: {result['duration_seconds']} s_", ""]
    if failures is not None:
        lines += ["## Thresholds", ""]
        lines += [f"- FAIL: {failure}" for failure in failures] or ["All thresholds met."]
        lines.append("")
    path.write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", action="append", required=True, choices=[*SUITES, *GROUPS],
                        help="suite to run (repeatable)")
    parser.add_argument("--output-dir", type=Path, help="where to write results (default: evals/results/<timestamp>)")
    parser.add_argument("--check-thresholds", nargs="?", type=Path, const=THRESHOLDS_FILE, metavar="FILE",
                        help=f"fail when metrics miss the thresholds (default file: {THRESHOLDS_FILE.name})")
    parser.add_argument("--limit", type=int, help="evaluate only the first N items (LLM suites)")
    parser.add_argument("--llm", action="store_true", help="risk suite: also score with the AI review (needs a key)")
    parser.add_argument("--retrieval-mode", choices=("vector", "hybrid"),
                        help="rag-answer suite: override RAG_RETRIEVAL_MODE")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("evals").setLevel(logging.INFO)

    suites = selected_suites(args.suite)
    env = environment(argv)
    output = args.output_dir or RESULTS_DIR / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output.mkdir(parents=True, exist_ok=True)
    ctx = Context(limit=args.limit, use_llm=args.llm, retrieval_mode=args.retrieval_mode)

    async def _run_all() -> dict[str, dict]:
        return {name: await run_suite(name, ctx) for name in suites}

    results = asyncio.run(_run_all())
    failures = None
    if args.check_thresholds:
        failures = check_thresholds(results, json.loads(args.check_thresholds.read_text()), suites)

    (output / "results.json").write_text(json.dumps({"run": env, "suites": results}, indent=2, default=str) + "\n")
    write_summary(output / "summary.md", env, results, failures)
    print(f"Results written to {output}")
    for name, result in results.items():
        print(f"  {name}: {result['status']}" + (f" ({result.get('reason')})" if result["status"] != "ok" else ""))
    if failures:
        print("Threshold failures:", *failures, sep="\n  ", file=sys.stderr)
        return 1
    if any(result["status"] == "error" for result in results.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
