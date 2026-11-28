"""
IntelliClaim AI - Request tracing and stored AI usage

Request spans (TracingMiddleware), the X-Trace-Id header, provider spans
nested under them, and the ai_usage counters on documents and claims.
"""

from opentelemetry.trace import SpanKind

from config import settings
from services.tracing import TRACE_ID_HEADER

EXTRACTION = {"claim_number": "CLM-7001", "patient_name": "John Doe", "treatment_cost": 28500}
REVIEW = {"risk_flags": [], "ai_risk_score": 10, "summary": "Looks consistent."}
GROQ_CALL_COST = (100 * 0.15 + 20 * 0.60) / 1e6  # the fake's usage at the default Groq price


def _server_span(spans):
    (span,) = [s for s in spans.get_finished_spans() if s.kind == SpanKind.SERVER]
    return span


async def test_request_span_is_named_after_the_route(async_client, spans):
    response = await async_client.get("/api/documents/doc-test-001")

    span = _server_span(spans)
    assert span.name == "GET /api/documents/{document_id}"
    assert span.attributes["http.route"] == "/api/documents/{document_id}"
    assert span.attributes["url.path"] == "/api/documents/doc-test-001"
    assert span.attributes["http.response.status_code"] == 200
    assert response.headers[TRACE_ID_HEADER] == format(span.context.trace_id, "032x")


async def test_request_span_continues_the_callers_trace(async_client, spans):
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    headers = {"traceparent": f"00-{trace_id}-00f067aa0ba902b7-01"}

    response = await async_client.get("/api/documents/missing", headers=headers)

    span = _server_span(spans)
    assert format(span.context.trace_id, "032x") == trace_id
    assert format(span.parent.span_id, "016x") == "00f067aa0ba902b7"
    assert response.status_code == 404
    assert span.status.is_unset  # client errors are not span errors


async def test_unhandled_error_marks_the_request_span(async_client, spans, monkeypatch):
    from routers import documents

    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(documents, "get_database", broken)
    response = await async_client.get("/api/documents/doc-test-001")

    span = _server_span(spans)
    assert response.status_code == 500
    assert span.attributes["http.response.status_code"] == 500
    assert not span.status.is_ok


async def test_extraction_cost_is_stored_on_the_document(async_client, test_db, fake_groq, spans):
    fake_groq.respond(EXTRACTION)

    data = (await async_client.post("/api/extract/doc-test-001")).json()

    assert data["ai_usage"] == {
        "calls": 1,
        "input_tokens": 100,
        "output_tokens": 20,
        "cost_usd": round(GROQ_CALL_COST, 8),
        "unpriced_calls": 0,
    }
    doc = await test_db.documents.find_one({"_id": "doc-test-001"})
    assert doc["ai_usage"]["extraction"] == data["ai_usage"]
    assert doc["ai_usage"]["total"]["calls"] == 1

    # The provider span is a child of the request span.
    server = _server_span(spans)
    (chat,) = [s for s in spans.get_finished_spans() if s.name.startswith("chat ")]
    assert chat.parent.span_id == server.context.span_id
    assert chat.context.trace_id == server.context.trace_id


async def test_repeated_extractions_add_up(async_client, test_db, fake_groq):
    fake_groq.respond(EXTRACTION, EXTRACTION)

    await async_client.post("/api/extract/doc-test-001")
    await async_client.post("/api/extract/doc-test-001")

    usage = (await test_db.documents.find_one({"_id": "doc-test-001"}))["ai_usage"]
    assert usage["extraction"]["calls"] == 2
    assert usage["total"]["input_tokens"] == 200


async def test_failed_extraction_still_records_the_spend(async_client, test_db, fake_groq):
    """The provider answered (and billed) with unusable output: no claim, but the cost is kept."""
    fake_groq.respond("not json")

    response = await async_client.post("/api/extract/doc-test-001")

    assert response.status_code == 502
    doc = await test_db.documents.find_one({"_id": "doc-test-001"})
    assert doc["claim_id"] is None
    assert doc["ai_usage"]["extraction"]["calls"] == 1


async def test_mock_extraction_records_no_usage(async_client, test_db, mock_llm):
    data = (await async_client.post("/api/extract/doc-test-001")).json()

    assert data["ai_usage"]["calls"] == 0
    assert "ai_usage" not in await test_db.documents.find_one({"_id": "doc-test-001"})


async def test_validation_cost_is_stored_on_the_claim(async_client, test_db, fake_groq):
    fake_groq.respond(REVIEW)

    response = await async_client.post("/api/validate/claim-test-002")

    assert response.status_code == 200
    claim = await test_db.claims.find_one({"_id": "claim-test-002"})
    assert claim["ai_usage"]["validation"]["calls"] == 1
    assert claim["ai_usage"]["total"]["cost_usd"] == round(GROQ_CALL_COST, 8)


async def test_rag_answers_through_langchain_are_traced(async_client, fake_groq, spans):
    assert (await async_client.post("/api/rag/index/doc-test-001")).status_code == 200
    fake_groq.respond("The treatment cost was $28,500 [1].")
    spans.clear()

    await async_client.post("/api/rag/query", json={"question": "appendicitis treatment cost"})

    (chat,) = [s for s in spans.get_finished_spans() if s.name.startswith("chat ")]
    assert chat.attributes["gen_ai.request.model"] == settings.GROQ_MODEL
    assert chat.parent.span_id == _server_span(spans).context.span_id
