"""
Generate the evaluation dataset (run from backend/).

    python -m evals.dataset.generate              write the ground-truth JSON and render the PDFs
    python -m evals.dataset.generate --json-only  only write the JSON
    python -m evals.dataset.generate --check      exit 1 if the committed JSON differs from a fresh build

The JSON files (documents, questions, risk claims) are committed. The PDFs
(about 20 MB with the scanned variants) are rendered into
evals/data/generated/ on demand; the suites render them when missing.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from evals.dataset.documents import SEED, build_documents
from evals.dataset.risk_claims import build_risk_claims
from evals.paths import DATA_DIR, DOCUMENTS_FILE, QA_FILE, RISK_CLAIMS_FILE


def _dump(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def ground_truth() -> dict[Path, str]:
    """The ground-truth files and their exact contents."""
    documents, questions = build_documents(SEED)
    return {
        DOCUMENTS_FILE: _dump({"seed": SEED, "documents": documents}),
        QA_FILE: _dump({"seed": SEED, "questions": questions}),
        RISK_CLAIMS_FILE: _dump(build_risk_claims()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="compare the committed JSON with a fresh build")
    parser.add_argument("--json-only", action="store_true", help="write the JSON but do not render PDFs")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    files = ground_truth()
    if args.check:
        drift = [path.name for path, content in files.items() if not path.exists() or path.read_text() != content]
        if drift:
            print(f"Ground truth differs from a fresh build: {', '.join(drift)}", file=sys.stderr)
            return 1
        print("Ground truth matches a fresh build.")
        return 0

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in files.items():
        path.write_text(content)
        print(f"wrote {path.relative_to(DATA_DIR.parent.parent)}")
    if not args.json_only:
        from evals.dataset.render import GENERATED_DIR, ensure_rendered

        ensure_rendered(json.loads(files[DOCUMENTS_FILE])["documents"])
        print(f"rendered PDFs into {GENERATED_DIR.relative_to(DATA_DIR.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
