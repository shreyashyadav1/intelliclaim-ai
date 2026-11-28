"""
IntelliClaim AI - Tracing and AI usage accounting

OpenTelemetry spans for every API request (TracingMiddleware) and every AI
provider call (TracedCompletions), with token usage and the estimated cost
on each provider span. Spans continue the caller's W3C traceparent, and each
response names its trace in an X-Trace-Id header.

Exporting is opt-in (TRACING_ENABLED): without it spans are still created,
so trace ids exist for correlation, but nothing leaves the process.

track_usage() adds up the provider calls made inside it, including calls
from tasks it starts, and store_usage() adds them to a document's or a
claim's ai_usage counters, per stage and in total.
"""

import contextlib
import logging
import time
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import settings

logger = logging.getLogger("intelliclaim.tracing")

TRACER_NAME = "intelliclaim"
TRACE_ID_HEADER = "X-Trace-Id"

_provider: TracerProvider | None = None


def configure_tracing(service_version: str) -> TracerProvider | None:
    """Install the process's TracerProvider (once); export spans when TRACING_ENABLED.

    Returns None when a provider was already installed, for example by tests.
    """
    global _provider
    if _provider is not None or isinstance(trace.get_tracer_provider(), TracerProvider):
        return None
    resource = Resource.create({"service.name": settings.OTEL_SERVICE_NAME, "service.version": service_version})
    provider = TracerProvider(resource=resource)
    if settings.TRACING_ENABLED:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        logger.info("Exporting traces to %s", endpoint)
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def shutdown_tracing() -> None:
    """Flush and stop the provider installed by configure_tracing."""
    global _provider
    if _provider is not None:
        _provider.shutdown()
        _provider = None


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(TRACER_NAME)


def trace_id_hex(span: trace.Span) -> str | None:
    context = span.get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


# --- Cost and usage -------------------------------------------------------------------


def price_per_mtok(provider: str) -> tuple[float, float] | None:
    """(input, output) USD per million tokens for `provider`, or None when not configured."""
    if provider == "groq":
        prices = (settings.GROQ_INPUT_USD_PER_MTOK, settings.GROQ_OUTPUT_USD_PER_MTOK)
    elif provider == "openai":
        prices = (settings.OPENAI_INPUT_USD_PER_MTOK, settings.OPENAI_OUTPUT_USD_PER_MTOK)
    else:
        return None
    if prices[0] is None or prices[1] is None:
        return None
    return prices


def estimate_cost_usd(provider: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = price_per_mtok(provider)
    if prices is None:
        return None
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1e6


@dataclass
class Usage:
    """Provider calls added up by track_usage().

    cost_usd covers the priced calls only; unpriced_calls counts the rest, so
    a partial total is never mistaken for a complete one.
    """

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    unpriced_calls: int = 0

    def add(self, input_tokens: int, output_tokens: int, cost_usd: float | None) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if cost_usd is None:
            self.unpriced_calls += 1
        else:
            self.cost_usd += cost_usd

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 8),
            "unpriced_calls": self.unpriced_calls,
        }

    def as_increment(self, prefix: str) -> dict[str, int | float]:
        """A MongoDB $inc document that adds this usage to the counters under `prefix`."""
        return {f"{prefix}.{key}": value for key, value in self.as_dict().items()}


_active_usage: ContextVar[tuple[Usage, ...]] = ContextVar("intelliclaim_usage", default=())


@contextlib.contextmanager
def track_usage() -> Iterator[Usage]:
    """Add up every provider call made inside the block (nested blocks each see their own calls)."""
    usage = Usage()
    token = _active_usage.set((*_active_usage.get(), usage))
    try:
        yield usage
    finally:
        _active_usage.reset(token)


async def store_usage(collection: Any, record_id: str, stage: str, usage: Usage) -> None:
    """Add `usage` to a stored record's ai_usage.<stage> and ai_usage.total counters.

    A no-op when no provider was called. Spend is recorded even when the step
    itself failed, because the provider still billed for it.
    """
    if usage.calls == 0:
        return
    increment = {**usage.as_increment(f"ai_usage.{stage}"), **usage.as_increment("ai_usage.total")}
    await collection.update_one({"_id": record_id}, {"$inc": increment})


def _record_usage(input_tokens: int, output_tokens: int, cost_usd: float | None) -> None:
    for usage in _active_usage.get():
        usage.add(input_tokens, output_tokens, cost_usd)


# --- Provider calls -------------------------------------------------------------------


class TracedCompletions:
    """Wraps an SDK `chat.completions` resource: one client span per completion.

    Used for direct calls (services.llm) and handed to the LangChain chat
    models as their async client, so the RAG chain's calls are traced too.
    create() and with_raw_response.create() (which ChatOpenAI uses) are
    traced; everything else is passed through to the wrapped resource.
    """

    def __init__(self, provider: str, completions: Any) -> None:
        self._provider = provider
        self._completions = completions

    def __getattr__(self, name: str) -> Any:
        return getattr(self._completions, name)

    async def create(self, **kwargs: Any) -> Any:
        return await self._traced(self._completions.create, kwargs, lambda response: response)

    @property
    def with_raw_response(self) -> Any:
        raw = self._completions.with_raw_response

        async def create(**kwargs: Any) -> Any:
            return await self._traced(raw.create, kwargs, lambda response: response.parse())

        return _RawResponseCreate(create)

    async def _traced(self, call: Any, kwargs: dict[str, Any], completion_of: Any) -> Any:
        model = kwargs.get("model", "")
        attributes = {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": self._provider,
            "gen_ai.request.model": model,
        }
        for key in ("temperature", "max_tokens"):
            if kwargs.get(key) is not None:
                attributes[f"gen_ai.request.{key}"] = kwargs[key]

        with get_tracer().start_as_current_span(f"chat {model}", kind=SpanKind.CLIENT, attributes=attributes) as span:
            started = time.perf_counter()
            response = await call(**kwargs)
            span.set_attribute("intelliclaim.llm.duration_ms", round((time.perf_counter() - started) * 1000, 1))

            completion = completion_of(response)
            usage = getattr(completion, "usage", None)
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
            cost = estimate_cost_usd(self._provider, input_tokens, output_tokens)
            span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
            if cost is not None:
                span.set_attribute("intelliclaim.llm.cost_usd", cost)
            response_model = getattr(completion, "model", None)
            if isinstance(response_model, str):
                span.set_attribute("gen_ai.response.model", response_model)
            _record_usage(input_tokens, output_tokens, cost)
            return response


@dataclass(frozen=True)
class _RawResponseCreate:
    create: Any


# --- Requests -------------------------------------------------------------------------


def _route_template(scope: Scope) -> str | None:
    """The matched route as a template (/api/documents/{document_id}), or None when nothing matched.

    Built from the request path and its path parameters, because the matched
    route of an included router carries only its path inside that router.
    """
    if scope.get("route") is None:
        return None
    segments = scope.get("path", "").split("/")
    for name, value in (scope.get("path_params") or {}).items():
        for index in range(len(segments) - 1, -1, -1):
            if segments[index] == str(value):
                segments[index] = f"{{{name}}}"
                break
    return "/".join(segments)


class TracingMiddleware:
    """A server span per HTTP request, continuing the caller's traceparent.

    Installed outermost, so the status recorded is the one the client gets
    (including the JSON 500s from UnhandledErrorMiddleware). The span is
    renamed to the matched route template once routing has run, so ids stay
    out of span names.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        carrier = {key.decode("latin-1"): value.decode("latin-1") for key, value in scope.get("headers", [])}
        method = scope.get("method", "GET")
        attributes = {"http.request.method": method, "url.path": scope.get("path", "")}
        status_code = 500

        with get_tracer().start_as_current_span(
            method, context=extract(carrier), kind=SpanKind.SERVER, attributes=attributes
        ) as span:
            trace_id = trace_id_hex(span)

            async def send_with_trace_id(message: Message) -> None:
                nonlocal status_code
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    if trace_id:
                        MutableHeaders(scope=message)[TRACE_ID_HEADER] = trace_id
                await send(message)

            try:
                await self.app(scope, receive, send_with_trace_id)
            finally:
                route = _route_template(scope)
                if route:
                    span.set_attribute("http.route", route)
                    span.update_name(f"{method} {route}")
                span.set_attribute("http.response.status_code", status_code)
                if status_code >= 500:
                    span.set_status(Status(StatusCode.ERROR))
