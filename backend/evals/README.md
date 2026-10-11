# IntelliClaim evaluation harness

Measures the document pipeline (retrieval, OCR, classification, rule-based
risk scoring, and with a Groq key, field extraction and RAG answers) against
a synthetic, labelled dataset. Every suite runs the application's own code:
`utils.pdf_parser` for text and OCR, `services.rag_index` / `rag_chain` /
`rag_service` for search and answers, `OCRService`, `ValidationService` and
`ExtractionService`. Nothing is re-implemented for the benchmark.

## Running it

From `backend/`, with the development requirements installed
(`pip install -r requirements-dev.txt`):

```bash
python -m evals.run --suite retrieval        # one suite
python -m evals.run --suite offline          # retrieval, ocr, classification, risk
python -m evals.run --suite offline --check-thresholds   # what CI runs
python -m evals.run --suite extraction --limit 20        # LLM suites, first 20 items
python -m evals.run --suite all              # everything (LLM suites skip without a key)
```

Each run writes `results.json` (metrics, per-item details, command, commit,
package versions) and `summary.md` to `evals/results/<UTC timestamp>/`, or to
`--output-dir`. Both are gitignored.

| Suite | Needs | What it measures |
|---|---|---|
| `retrieval` | nothing (fastembed downloads BAAI/bge-small-en-v1.5 once, about 67 MB) | recall@1/3/5, MRR@10 and answer-in-top-5 for vector and hybrid retrieval; grid over chunk size and fusion weights |
| `ocr` | the `tesseract` binary; skipped cleanly when missing | character and word error rates of scanned PDFs (Tesseract) and text PDFs (text layer) against the ground truth |
| `classification` | nothing (the LLM path needs `OPENAI_API_KEY`) | accuracy, per-class precision/recall/F1 and confusion matrix |
| `risk` | MongoDB for the duplicate check; skipped when unreachable | PR-AUC, ROC-AUC and precision/recall at score thresholds of the rule-based risk score, including the configured `RISK_FLAG_THRESHOLD` and the threshold with the best F1; per-anomaly rule detection. `--llm` adds the AI review (needs `GROQ_API_KEY`) |
| `extraction` | `GROQ_API_KEY`; skipped with a message when unset | per-field precision/recall/F1 and exact match on text and scanned PDFs, latency p50/p95, tokens and cost per document |
| `rag-answer` | `GROQ_API_KEY`; skipped with a message when unset | answer accuracy, citation hit rate and precision, abstention on unanswerable questions, latency, tokens and cost |

Environment variables (all optional):

| Variable | Used by | Default |
|---|---|---|
| `EVAL_MONGODB_URI` | risk | `TEST_MONGODB_URI`, then `mongodb://localhost:27017`. A throwaway `intelliclaim_eval_<pid>` database is created and dropped |
| `FASTEMBED_CACHE_PATH` | retrieval, rag-answer | the application setting: where the embedding model is cached |
| `GROQ_API_KEY`, `GROQ_MODEL` | extraction, rag-answer, risk `--llm` | the application settings. The LLM suites send requests to Groq only, even when `OPENAI_API_KEY` is also set |
| `EVAL_GROQ_INPUT_USD_PER_MTOK`, `EVAL_GROQ_OUTPUT_USD_PER_MTOK` | cost estimates | 0.15 and 0.60, Groq's list price for openai/gpt-oss-120b, the default `GROQ_MODEL` (https://console.groq.com/docs/models, checked 2026-10-05). Check it before relying on the cost figures |
| `EVAL_RATE_LIMIT_RETRIES`, `EVAL_RATE_LIMIT_BACKOFF_SECONDS` | LLM suites | 6 retries, 10 s times the attempt number, when Groq rate-limits |
| `EVAL_GIT_COMMIT` | run metadata | records the commit when git is unavailable (for example in a container) |

## The dataset

`python -m evals.dataset.generate` builds everything from a fixed seed (`SEED
= 7341` in `evals/dataset/documents.py`), so the same code and package versions
always produce the same data; `--check` exits 1 if the committed JSON differs
from a fresh build, and a unit test does the same check.

- **60 documents** from 24 patient episodes: 24 medical invoices, 12
  outpatient medical reports, 12 two-page discharge summaries and 12 policy
  summaries. People come from Faker with a fixed seed; hospitals, insurers and
  plans are invented names; provider IDs use a `PRV-` prefix instead of the
  NPI format; phone numbers use the 555-01xx range; every page says the
  document is synthetic and fictional. Nothing is modelled on insurer portals,
  call transcripts, identity checks or benefits verification.
- **Ground truth** (`data/documents.json`): the class label (policy summaries
  are `policy_document`), the exact page texts, and the eleven extraction
  fields both normalised (ISO dates, numeric cost) and as printed. Fields a
  document does not state are `null`.
- **228 questions** (`data/qa.json`) from templates over the ground truth, each
  tied to one source document: 96 identifier questions ("What is the total
  amount due on invoice INV-2632?"), 72 descriptive ones that name the patient
  and use the document's wording, 48 paraphrases that name the patient but
  avoid the document's labels ("What was the final bill for ...'s care?"), and
  12 unanswerable questions (for example a deductible on an invoice).
- **Risk claims** (`data/risk_claims.json`): a 60-claim history and 206
  incoming claims, 86 with labelled anomalies: duplicates (exact, different
  case or spacing, a typo in the name), cost outliers (above $150,000,
  $55,000-$140,000, or 8-15 times the usual cost but under $50,000), date
  inconsistencies (discharge before admission, stays over 90 days, service
  after discharge) and missing fields (one or two required, three or more,
  optional only). Six claims carry two anomalies. Some variants are ones the
  rules are not designed to catch, and 10 clean claims are legitimately
  expensive or elective procedures.

The JSON is committed. The rendered PDFs are not: text PDFs (480 KB) plus
scanned variants (28 MB) total 29 MB, over the 5 MB limit for committed
binaries, so the suites render them on demand into `data/generated/`
(gitignored, rebuilt when the ground truth or renderer changes). Scans are the
text PDFs rasterised at 200 dpi, rotated by up to 1.5 degrees, lightly blurred,
given Gaussian noise (sigma 10) and saved as JPEG in image-only PDFs; the
application reads them back through OCR at 300 dpi.

## Results

Numbers below come from these runs (no API key was available, so the
extraction and rag-answer suites were not run):

| Run | Command (from `backend/`) | Date (UTC) | Commit | Platform |
|---|---|---|---|---|
| A | `python -m evals.run --suite retrieval --suite classification --suite risk --check-thresholds` with `EVAL_MONGODB_URI=mongodb://localhost:27022` | 2026-10-11 00:35 | `c527d08` | macOS 26.5 arm64, Python 3.13.14 |
| B | `python -m evals.run --suite offline --check-thresholds --output-dir /out/offline` in `python:3.13-slim` with tesseract-ocr | 2026-10-11 00:37 | `c527d08` | Debian 13 arm64 (Docker), Python 3.13.15, tesseract 5.5.0 |
| C | `python -m evals.run --suite ocr --output-dir /out` in `ubuntu:24.04` with tesseract-ocr | 2026-10-11 00:44 | `c527d08` | Ubuntu 24.04 arm64 (Docker), Python 3.12.3, tesseract 5.3.4 |

Run B repeated every offline suite on Linux: classification and risk were
identical to run A, and retrieval differed only in near-ties (10 of 216
questions moved by a rank or so: recall@1, recall@5 and answer-in-top-5
identical, recall@3 within 0.005, MRR within 0.001). Run C, with the tesseract
version of CI's Ubuntu image, gave OCR metrics identical to run B. On one
machine runs are deterministic: repeating a run gives identical metrics.

The first runs, on 2026-09-29, measured the same retrieval, OCR and risk-score
results. Since then the keyword classifier gained a `policy_document` class
(commit `fcb47d1`: accuracy 0.800 to 1.000), the flagged-claims list starts at
a risk score of 15 instead of 30 (`cb19f1f`: recall 0.093 to 0.767), and
langchain-community was replaced by adapters on langchain-core (`296f496`).
Neither that replacement nor the switch of the default Groq model to
`openai/gpt-oss-120b` changed any offline metric or per-question rank: runs on
2026-10-05, before the model switch, gave the same results as runs A to C.

### Retrieval (run A)

216 answerable questions over 60 documents, production settings: 384-token
chunks (72 chunks, one per page), BAAI/bge-small-en-v1.5, hybrid = vector +
BM25 by weighted reciprocal rank fusion (weights 0.5/0.5, k = 60). "Answer in
top 5" means a top-5 chunk from the source document contains the answer as
printed, which is what the model sees with the API's default `top_k=5`.

| Mode | Recall@1 | Recall@3 | Recall@5 | MRR@10 | Answer in top 5 |
|---|---|---|---|---|---|
| vector | 0.449 | 0.616 | 0.653 | 0.553 | 0.625 |
| hybrid | 0.648 | 0.843 | 0.907 | 0.756 | 0.875 |

By question style (recall@1 / recall@5 / MRR):

| Style | Vector | Hybrid |
|---|---|---|
| identifier (96) | 0.083 / 0.240 / 0.186 | 0.500 / 0.792 / 0.608 |
| descriptive (72) | 0.736 / 1.000 / 0.854 | 0.736 / 1.000 / 0.866 |
| paraphrase (48) | 0.750 / 0.958 / 0.835 | 0.813 / 1.000 / 0.887 |

By source document (recall@1 / recall@5 / MRR): invoices 0.202 / 0.476 / 0.349
vector vs 0.321 / 0.833 / 0.534 hybrid; policy summaries 0.500 / 0.667 / 0.595
vs 0.875 / 0.979 / 0.918; medical reports 0.528 / 0.750 / 0.621 vs 0.667 /
0.889 / 0.759; discharge summaries 0.771 / 0.875 / 0.817 vs 0.979 / 0.979 /
0.979. Retrieval latency per question: vector p50 7.1 ms / p95 18.8 ms, hybrid
9.8 / 26.5 ms (run A hardware, shared with other work, so treat these as rough).

Embeddings do not tell invoices apart by number: identifier questions reach a
source chunk in the top five 24% of the time with vector search and 79% with
hybrid.

### How the retrieval default was chosen

Grid from run A. Each cell: recall@1 / recall@5 / MRR / answer-in-top-5 over
all 216 questions, then MRR per style (identifier, descriptive, paraphrase).
512-token chunks give exactly the 384-token results (every page already fits in
one chunk) and are omitted.

| Chunks | Configuration (vector/BM25) | All questions | MRR identifier / descriptive / paraphrase |
|---|---|---|---|
| 128 (147) | vector | 0.435 / 0.634 / 0.527 / 0.380 | 0.166 / 0.852 / 0.761 |
| 128 (147) | hybrid 0.5/0.5 | 0.593 / 0.801 / 0.678 / 0.518 | 0.438 / 0.880 / 0.853 |
| 256 (84) | vector | 0.412 / 0.657 / 0.524 / 0.611 | 0.182 / 0.819 / 0.767 |
| 256 (84) | hybrid 0.5/0.5 | 0.602 / 0.838 / 0.708 / 0.768 | 0.553 / 0.816 / 0.855 |
| 384 (72) | vector | 0.449 / 0.653 / 0.553 / 0.625 | 0.186 / 0.854 / 0.835 |
| 384 (72) | hybrid 0.7/0.3 | 0.546 / 0.796 / 0.654 / 0.755 | 0.382 / 0.855 / 0.898 |
| 384 (72) | **hybrid 0.5/0.5** | **0.648 / 0.907 / 0.756 / 0.875** | **0.608 / 0.866 / 0.887** |
| 384 (72) | hybrid 0.3/0.7 | 0.708 / 0.958 / 0.821 / 0.926 | 0.776 / 0.875 / 0.828 |
| 384 (72) | hybrid 0.2/0.8 | 0.764 / 0.958 / 0.852 / 0.926 | 0.855 / 0.882 / 0.802 |
| 384 (72) | hybrid 0.1/0.9 | 0.778 / 0.963 / 0.865 / 0.963 | 0.915 / 0.882 / 0.740 |

(`summary.md` of a retrieval run has every combination.)

The rule, fixed before choosing:

1. **Chunk size**: the best vector-only answer-in-top-5. 384 tokens (0.625)
   beats 256 (0.611) and 128 (0.380); 512 ties with 384, and 384 is kept
   because it stays inside the embedding model's 512-token input on denser
   pages.
2. **Mode and weights**: at that chunk size, the highest answer-in-top-5 among
   configurations that do not lower any question style's MRR below
   vector-only.

Hybrid 0.5/0.5 is the best configuration that passes: 0.875 answer-in-top-5
against 0.625 for vector search, and every style's MRR improves. BM25-heavier weights
score higher overall on this dataset but rank paraphrased questions below
vector search (paraphrase MRR 0.828 at 0.3/0.7, 0.740 at 0.1/0.9 versus 0.835).
Every question here names a patient or a document number, which favours
keyword matching, so the rule protects the case where the embeddings do the
work. Hence `RAG_RETRIEVAL_MODE=hybrid`, `RAG_CHUNK_SIZE = 384`,
`RAG_CHUNK_OVERLAP = 48` and `HYBRID_WEIGHTS = (0.5, 0.5)` in `config.py`.

### OCR (runs B and C, identical)

72 pages from 60 documents.

| Path | CER mean | CER median | CER p90 | CER max | WER mean | Field values recovered verbatim |
|---|---|---|---|---|---|---|
| text layer (PyMuPDF) | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 1.000 |
| scanned (Tesseract 5.5.0 and 5.3.4) | 0.0005 | 0.0000 | 0.0014 | 0.0041 | 0.0039 | 0.966 |

Character errors on these mild scans are rare, but every miss lands on the
diagnosis line: 15 of the 60 scans do not reproduce the printed diagnosis
(description and ICD-10 code) character for character, which matters because
extraction copies that field. OCR took 1.8 s per page in run B and 1.7 s in run C.

### Classification (runs A and B, identical)

Keyword classifier (the path used whenever `OPENAI_API_KEY` is unset,
including the Groq deployment): **accuracy 1.000, macro F1 1.000** on the 60
text-layer documents. Every invoice, medical report, discharge summary and
policy summary gets its own class.

Until commit `fcb47d1` the application had no class for insurance policies:
accuracy was 0.800 and macro F1 0.750, because all 12 policy summaries were
predicted `claim_form` (they share "policyholder" and "coverage" with the
claim-form keywords). The fix adds `policy_document` with policy vocabulary
(deductible, coinsurance, premium, coverage period and similar) and moves those
two terms out of the claim-form list.

Read the 1.000 with care: the keyword lists were revised with these documents
in view, and the documents come from a few fixed templates, so this shows that
the rules separate the classes, not how well they generalise. Unit tests
(`tests/test_services/test_classification.py`) add a differently worded policy
certificate and a claim form that names the policyholder. The dataset has no
claim forms, so `claim_form` precision and recall are not measured. The LLM
classifier was not run: the application only uses it with OpenAI, and no key
was configured.

### Risk (runs A and B, identical)

206 claims (86 anomalous, 120 clean), rules only: **PR-AUC 0.805, ROC-AUC
0.844**; mean score 17.79 for anomalous claims and 2.25 for clean ones.

| Flag when score >= | Precision | Recall | F1 | Flagged (true + false positives) |
|---|---|---|---|---|
| 5 | 0.767 | 0.767 | 0.767 | 86 (66 + 20) |
| **15 (`RISK_FLAG_THRESHOLD`: flagged-claims list, medium risk)** | **0.795** | **0.767** | **0.781** | 83 (66 + 17) |
| 25 | 1.000 | 0.477 | 0.646 | 41 (41 + 0) |
| 30 (the flagged-claims list before commit `cb19f1f`) | 1.000 | 0.093 | 0.170 | 8 (8 + 0) |
| 40 | 1.000 | 0.081 | 0.150 | 7 (7 + 0) |
| 50 | 1.000 | 0.023 | 0.045 | 2 (2 + 0) |
| 60 (high risk) | 0.000 | 0.000 | 0.000 | 0 |

Rule weights are 25 (high severity), 15 (medium) and 5 (low), so rule-only
scores here take just the values 0, 5, 15, 25, 30, 40 and 50; a threshold
between two of them flags the same claims as the next one (`summary.md` also
lists 10 and 20).

The matching rule fired for every exact or case/spacing duplicate, cost above
$55,000, discharge before admission, stay over 90 days and missing required
field, and for none of the name-typo duplicates, cost outliers under $50,000,
services dated after discharge or claims missing only optional fields. 16.7%
of clean claims raise at least one rule flag (the expensive and elective
procedures). At 15, all 17 false positives are clean claims whose only finding
is a cost between $50,000 and $150,000, and all 20 missed anomalies score 0:
no rule covers them (7 cost outliers under $50,000, 6 name-typo duplicates, 5
services after discharge, 2 claims missing only optional fields).

### How the flagged-claims threshold was chosen

The flagged-claims list used to start at 30. A single rule finding scores at
most 25, so on rules alone only claims with two findings reached it, and it
held 8 of the 86 anomalous claims. The rule for the new threshold, fixed before
the sweep: the threshold with the highest F1 over every observed rule-based
score, ties going to the higher threshold (fewer claims to review for the same
F1).

15 wins with F1 0.781; the runner-up, 5, flags 3 more clean claims (the
elective-procedure keyword) and no more anomalies. So `RISK_FLAG_THRESHOLD`
defaults to 15 in `config.py`: medium risk and the flagged-claims list start
at 15, which one medium- or high-severity finding reaches, and high risk stays
at 60, where validation also sets the claim's status to `flagged`. A test
(`tests/test_evals/test_runner.py`) fails if the rule stops picking the
configured default, for example after the rule weights change.

Two caveats: the threshold is chosen and measured on the same 206 claims (with
seven distinct scores there is little room to overfit, but it is still an
in-sample choice), and the AI review, which adds up to 40 points
(ai_risk_score x 0.4 x mean flag confidence), was not measured. With a Groq
key, `python -m evals.run --suite risk --llm` scores the claims again with the
review included and reports the same sweep.

### Extraction and RAG answers

Not measured: they need `GROQ_API_KEY`, which was not available. With a key:

```bash
python -m evals.run --suite extraction            # 60 documents x (text PDF, scanned PDF): 120 requests
python -m evals.run --suite rag-answer            # 228 questions: 228 requests
python -m evals.run --suite risk --llm --limit 50 # rules + AI review on 50 claims
```

Groq's free tier limits requests and tokens per minute; the suites wait and
retry when rate-limited, and `--limit` keeps a first run small.

## Thresholds and CI

`.github/workflows/backend-ci.yml` has an "Offline evals" job that installs
Tesseract, starts MongoDB, runs `python -m evals.run --suite offline
--check-thresholds` and uploads the results. `thresholds.json` sets each bound
slightly below the measured value, with more room where the platform matters:
retrieval near-ties shift between machines, and OCR could vary with the
tesseract version (runs B and C agree for 5.5.0 and 5.3.4, the version on CI's
Ubuntu image). Classification needs accuracy 0.98 and macro F1 0.97 (at most
one of the 60 documents misclassified); risk checks PR-AUC, ROC-AUC, and
precision and recall at the configured `RISK_FLAG_THRESHOLD`
(`rules.flagged`). Runs A and B met every threshold of the suites they ran
(both with `--check-thresholds`), and run C meets the OCR thresholds. A suite
that has thresholds but does not run (for example without tesseract) fails the
check. After an intentional change to the pipeline or the dataset, re-run the
suites and update the thresholds and this file from the new `summary.md`.

## Limitations

- The documents are synthetic and cleanly laid out, and every question names
  a patient or document number. Real uploads are messier; treat these numbers
  as regression baselines, not as estimates of production accuracy.
- The scans are mildly degraded, so OCR character error rates are close to
  zero; the verbatim field-recovery rate is the more telling figure.
- Answers are matched by normalised text, amounts and dates, not judged for
  quality by a model.
