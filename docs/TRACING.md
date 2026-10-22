# Tracing and AI cost

The API creates an OpenTelemetry trace for every request and a child span for
every AI provider call, and keeps a running total of tokens and estimated cost
on each document and claim. Code: `backend/services/tracing.py`.

## What is recorded

| Span | Kind | Attributes |
| --- | --- | --- |
| `POST /api/extract/{document_id}` (one per request, named after the route) | server | `http.request.method`, `http.route`, `url.path`, `http.response.status_code`; error status on 5xx |
| `chat openai/gpt-oss-120b` (one per completion) | client | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.request.temperature`, `gen_ai.request.max_tokens`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `intelliclaim.llm.cost_usd`, `intelliclaim.llm.duration_ms` |

- Provider spans cover every path: extraction, validation and document
  classification (`services/llm.py`) and RAG answers through the LangChain
  chain (ChatGroq calls `create`, ChatOpenAI calls `with_raw_response.create`;
  both go through `TracedCompletions`).
- A request that carries a W3C `traceparent` header continues that trace, so a
  caller's span is the parent of the API's request span.
- Every response has an `X-Trace-Id` header (exposed to browsers through CORS),
  so a slow or failed request can be found in the trace backend.
- Failed provider calls are error spans with the exception recorded and add no
  usage.

## Cost per document and per claim

Each stage adds its provider calls to counters on the stored record:

```json
"ai_usage": {
  "extraction": {"calls": 1, "input_tokens": 812, "output_tokens": 143, "cost_usd": 0.0002076, "unpriced_calls": 0},
  "total":      {"calls": 1, "input_tokens": 812, "output_tokens": 143, "cost_usd": 0.0002076, "unpriced_calls": 0}
}
```

(The numbers above come from a stub provider, not a real model.)

| Record | Stages |
| --- | --- |
| document | `upload` (classification, OpenAI only), `extraction` |
| claim | `validation` (single and batch) |

- `POST /api/extract/{document_id}` also returns the usage of that call as
  `ai_usage`.
- Spend is recorded even when the step fails after the provider answered (for
  example unusable output, which returns 502), because the provider still
  billed for it.
- Repeated runs add up; MongoDB `$inc` keeps concurrent updates correct.
- Mock mode and rule-only paths make no provider calls and record nothing.

Cost is estimated from the token counts the provider returns and the prices
in settings (USD per million tokens). The Groq defaults are the list price of
`openai/gpt-oss-120b` (0.15 input / 0.60 output, checked 2026-10-05); update
them together with `GROQ_MODEL`. OpenAI has no default price: its calls are
counted in `unpriced_calls` and left out of `cost_usd`, so a partial total is
never mistaken for a complete one.

## Settings

| Variable | Default | |
| --- | --- | --- |
| `TRACING_ENABLED` | `false` | Export spans over OTLP. Spans and trace ids exist either way; nothing leaves the process unless this is on. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint (Jaeger, Grafana Tempo, an OpenTelemetry Collector) |
| `OTEL_SERVICE_NAME` | `intelliclaim-api` | `service.name` on exported spans |
| `GROQ_INPUT_USD_PER_MTOK`, `GROQ_OUTPUT_USD_PER_MTOK` | `0.15`, `0.60` | Groq prices |
| `OPENAI_INPUT_USD_PER_MTOK`, `OPENAI_OUTPUT_USD_PER_MTOK` | empty | OpenAI prices; empty means unknown |

## Viewing traces locally

```bash
docker run --rm -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one:1.62.0
TRACING_ENABLED=true uvicorn main:app --reload   # from backend/
```

Upload and extract a document, then open http://localhost:16686 and pick the
`intelliclaim-api` service. The extraction request shows the provider call
nested under it with its tokens and cost.

## Tests

`tests/test_services/test_tracing.py` (cost, usage tracking, provider spans)
and `tests/test_routers/test_request_tracing.py` (request spans, trace
propagation, stored `ai_usage`) use an in-memory span exporter installed by
`tests/conftest.py`.
