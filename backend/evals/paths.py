"""Filesystem locations used by the evaluation harness."""

from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = EVALS_DIR.parent
DATA_DIR = EVALS_DIR / "data"
GENERATED_DIR = DATA_DIR / "generated"  # rendered PDFs, created on demand (gitignored)
RESULTS_DIR = EVALS_DIR / "results"  # one directory per run (gitignored)
THRESHOLDS_FILE = EVALS_DIR / "thresholds.json"

DOCUMENTS_FILE = DATA_DIR / "documents.json"
QA_FILE = DATA_DIR / "qa.json"
RISK_CLAIMS_FILE = DATA_DIR / "risk_claims.json"
