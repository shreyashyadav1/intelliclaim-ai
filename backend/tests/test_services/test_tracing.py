"""
IntelliClaim AI - Tracing and AI usage accounting (services.tracing)

Provider spans, cost estimates and usage tracking, without HTTP; the request
spans and stored ai_usage are covered in tests/test_routers/test_tracing.py.
"""

import asyncio

import pytest
from opentelemetry.trace import SpanKind

from config import EXTRACTION_PARAMS, Settings, settings
from services import llm, tracing


def test_groq_cost_uses_the_configured_list_price(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_INPUT_USD_PER_MTOK", 0.15)
    monkeypatch.setattr(settings, "GROQ_OUTPUT_USD_PER_MTOK", 0.60)
    assert tracing.estimate_cost_usd("groq", 1_000_000, 0) == pytest.approx(0.15)
    assert tracing.estimate_cost_usd("groq", 100, 20) == pytest.approx((100 * 0.15 + 20 * 0.60) / 1e6)


def test_cost_is_unknown_without_a_price(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_INPUT_USD_PER_MTOK", 2.5)
    monkeypatch.setattr(settings, "OPENAI_OUTPUT_USD_PER_MTOK", None)
    assert tracing.estimate_cost_usd("openai", 100, 20) is None
    assert tracing.estimate_cost_usd("mock", 100, 20) is None


def test_blank_prices_mean_unknown(monkeypatch):
    monkeypatch.setenv("OPENAI_INPUT_USD_PER_MTOK", "")
    monkeypatch.setenv("GROQ_OUTPUT_USD_PER_MTOK", " ")
    loaded = Settings()
    assert loaded.OPENAI_INPUT_USD_PER_MTOK is None
    assert loaded.GROQ_OUTPUT_USD_PER_MTOK is None


def test_usage_counts_unpriced_calls_separately():
    usage = tracing.Usage()
    usage.add(100, 20, 0.000027)
    usage.add(50, 10, None)
    assert usage.as_dict() == {
        "calls": 2,
        "input_tokens": 150,
        "output_tokens": 30,
        "cost_usd": 0.000027,
        "unpriced_calls": 1,
    }
    assert usage.as_increment("ai_usage.total")["ai_usage.total.unpriced_calls"] == 1


async def test_track_usage_sees_calls_from_tasks_and_nested_blocks():
    async def call(tokens: int) -> None:
        tracing._record_usage(tokens, 1, 0.5)

    with tracing.track_usage() as outer:
        await asyncio.gather(call(10), call(20))
        with tracing.track_usage() as inner:
            await call(5)
    await call(1000)  # outside every block: not counted

    assert (outer.calls, outer.input_tokens, outer.cost_usd) == (3, 35, 1.5)
    assert (inner.calls, inner.input_tokens) == (1, 5)


async def test_groq_call_is_a_client_span_with_usage_and_cost(fake_groq, spans, monkeypatch):
    monkeypatch.setattr(settings, "GROQ_INPUT_USD_PER_MTOK", 0.15)
    monkeypatch.setattr(settings, "GROQ_OUTPUT_USD_PER_MTOK", 0.60)
    fake_groq.respond("hello")

    with tracing.track_usage() as usage:
        await llm.groq_chat([{"role": "user", "content": "hi"}], EXTRACTION_PARAMS)

    (span,) = spans.get_finished_spans()
    assert span.name == f"chat {settings.GROQ_MODEL}"
    assert span.kind == SpanKind.CLIENT
    attributes = dict(span.attributes)
    assert attributes["gen_ai.provider.name"] == "groq"
    assert attributes["gen_ai.request.model"] == settings.GROQ_MODEL
    assert attributes["gen_ai.request.max_tokens"] == EXTRACTION_PARAMS.max_tokens
    assert attributes["gen_ai.usage.input_tokens"] == 100  # the fake's usage block
    assert attributes["gen_ai.usage.output_tokens"] == 20
    assert attributes["intelliclaim.llm.cost_usd"] == pytest.approx(27e-6)
    assert usage.calls == 1 and usage.cost_usd == pytest.approx(27e-6)


async def test_failed_call_is_an_error_span_and_costs_nothing(fake_groq, groq_errors, spans):
    fake_groq.respond(groq_errors.connection())

    with tracing.track_usage() as usage, pytest.raises(llm.LLMProviderError):
        await llm.groq_chat([{"role": "user", "content": "hi"}], EXTRACTION_PARAMS)

    (span,) = spans.get_finished_spans()
    assert not span.status.is_ok
    assert span.events[0].name == "exception"
    assert usage.calls == 0


async def test_each_json_validation_retry_is_its_own_span(fake_groq, groq_errors, spans, monkeypatch):
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 1)
    fake_groq.respond(groq_errors.json_validate(), '{"ok": true}')

    with tracing.track_usage() as usage:
        content = await llm.groq_chat([{"role": "user", "content": "json please"}], EXTRACTION_PARAMS, json_mode=True)

    assert content == '{"ok": true}'
    rejected, accepted = spans.get_finished_spans()
    assert not rejected.status.is_ok and rejected.events[0].name == "exception"
    assert accepted.status.is_unset and "gen_ai.usage.input_tokens" in dict(accepted.attributes)
    assert usage.calls == 1  # only the reply that came back has a usage block to bill


async def test_openai_raw_response_calls_are_traced(fake_openai, spans, monkeypatch):
    """ChatOpenAI calls with_raw_response.create; the span reads usage from the parsed completion."""
    monkeypatch.setattr(settings, "OPENAI_INPUT_USD_PER_MTOK", None)
    completions = tracing.TracedCompletions("openai", fake_openai.chat.completions)
    fake_openai.respond("answer")

    with tracing.track_usage() as usage:
        raw = await completions.with_raw_response.create(model="gpt-test", messages=[])

    assert raw.parse().choices[0].message.content == "answer"
    (span,) = spans.get_finished_spans()
    assert span.attributes["gen_ai.provider.name"] == "openai"
    assert span.attributes["gen_ai.usage.input_tokens"] == 100
    assert "intelliclaim.llm.cost_usd" not in span.attributes
    assert usage.as_dict()["unpriced_calls"] == 1


def test_configure_tracing_keeps_an_installed_provider():
    """The test session's provider is already installed, so configuring again changes nothing."""
    assert tracing.configure_tracing("test") is None
