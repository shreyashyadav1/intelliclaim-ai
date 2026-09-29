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
| `risk` | MongoDB for the duplicate check; skipped when unreachable | PR-AUC, ROC-AUC and precision/recall at score thresholds of the rule-based risk score; per-anomaly rule detection. `--llm` adds the AI review (needs `GROQ_API_KEY`) |
| `extraction` | `GROQ_API_KEY`; skipped with a message when unset | per-field precision/recall/F1 and exact match on text and scanned PDFs, latency p50/p95, tokens and cost per document |
| `rag-answer` | `GROQ_API_KEY`; skipped with a message when unset | answer accuracy, citation hit rate and precision, abstention on unanswerable questions, latency, tokens and cost |

Environment variables (all optional):

| Variable | Used by | Default |
|---|---|---|
| `EVAL_MONGODB_URI` | risk | `TEST_MONGODB_URI`, then `mongodb://localhost:27017`. A throwaway `intelliclaim_eval_<pid>` database is created and dropped |
| `FASTEMBED_CACHE_PATH` | retrieval, rag-answer | the application setting: where the embedding model is cached |
| `GROQ_API_KEY`, `GROQ_MODEL` | extraction, rag-answer, risk `--llm` | the application settings. The LLM suites send requests to Groq only, even when `OPENAI_API_KEY` is also set |
| `EVAL_GROQ_INPUT_USD_PER_MTOK`, `EVAL_GROQ_OUTPUT_USD_PER_MTOK` | cost estimates | 0.59 and 0.79, Groq's published list price for llama-3.3-70b-versatile (https://groq.com/pricing). Check it before relying on the cost figures |
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
- **Ground truth** (`data/documents.json`): the class label, the exact page
  texts, and the eleven extraction fields both normalised (ISO dates, numeric
  cost) and as printed. Policy summaries are labelled `other` because the
  application has no policy-summary class. Fields a document does not state
  are `null`.
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
| A | `python -m evals.run --suite retrieval --suite classification --suite risk` with `EVAL_MONGODB_URI=mongodb://localhost:27019` | 2026-09-29 03:06 | `4981e55` | macOS 26.5 arm64, Python 3.13.14 |
| B | `python -m evals.run --suite offline --output-dir /out/offline` in `python:3.13-slim` with tesseract-ocr | 2026-09-29 03:13 | `64d8b45` | Debian 13 arm64 (Docker), Python 3.13.15, tesseract 5.5.0 |
| C | `python3 -m evals.run --suite ocr --output-dir /out` in `ubuntu:24.04` with tesseract-ocr | 2026-09-29 03:25 | `64d8b45` | Ubuntu 24.04 arm64 (Docker), Python 3.12.3, tesseract 5.3.4 |

Commits `4981e55` and `64d8b45` differ only in the OCR suite's reporting. Run B
repeated the other offline suites on Linux: classification and risk were
identical, and retrieval differed only in near-ties (10 of 216 questions moved
by a rank or so: recall@1, recall@5 and answer-in-top-5 identical, recall@3
within 0.005, MRR within 0.001). Run C, with the tesseract version of CI's
Ubuntu image, gave OCR metrics identical to run B. On one machine runs are
deterministic: repeating run A gives identical metrics.

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
0.979. Retrieval latency per question: vector p50 6.6 ms / p95 13.7 ms, hybrid
9.2 / 20.3 ms (run A hardware).

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
extraction copies that field. OCR took 1.5 s per page (two CPU cores in
Docker).

### Classification (runs A and B, identical)

Keyword classifier (the path used whenever `OPENAI_API_KEY` is unset,
including the Groq deployment): **accuracy 0.800, macro F1 0.750**. All 48
invoices, medical reports and discharge summaries are classified correctly;
all 12 policy summaries are predicted `claim_form` (true class `other`)
because they share "policy number", "policyholder" and "coverage" with the
claim-form keywords. The LLM classifier was not run: the application
only uses it with OpenAI, and no key was configured.

### Risk (runs A and B, identical)

206 claims (86 anomalous, 120 clean), rules only: **PR-AUC 0.805, ROC-AUC
0.844**; mean score 17.79 for anomalous claims and 2.25 for clean ones.

| Flag when score >= | Precision | Recall | F1 |
|---|---|---|---|
| 15 | 0.795 | 0.767 | 0.781 |
| 25 | 1.000 | 0.477 | 0.646 |
| 30 (flagged-claims list) | 1.000 | 0.093 | 0.170 |
| 60 ("high" risk) | 0.000 | 0.000 | 0.000 |

The matching rule fired for every exact or case/spacing duplicate, cost above
$55,000, discharge before admission, stay over 90 days and missing required
field, and for none of the name-typo duplicates, cost outliers under $50,000,
services dated after discharge or claims missing only optional fields. 16.7%
of clean claims raise at least one rule flag (the expensive and elective
procedures). A single rule finding scores at most 25, so on rules alone only
claims with two findings reach the flagged-claims list (score 30 or more): the
AI review is what moves single findings over it.

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
Ubuntu image). All three runs meet every threshold. A suite that has
thresholds but does not run (for example without tesseract) fails the check.
After an intentional change to the pipeline or the dataset, re-run the suites
and update the thresholds and this file from the new `summary.md`.

## Limitations

- The documents are synthetic and cleanly laid out, and every question names
  a patient or document number. Real uploads are messier; treat these numbers
  as regression baselines, not as estimates of production accuracy.
- The scans are mildly degraded, so OCR character error rates are close to
  zero; the verbatim field-recovery rate is the more telling figure.
- Answers are matched by normalised text, amounts and dates, not judged for
  quality by a model.
