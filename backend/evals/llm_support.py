"""
Helpers for suites that call Groq (extraction, rag-answer, risk with --llm).

The application's code runs unchanged: UsageRecorder wraps the shared
AsyncGroq client that services.llm (and ChatGroq, through it) use, and
records latency and token usage of every request.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from evals.config import eval_settings

logger = logging.getLogger("evals.llm")

KEY_MISSING = "GROQ_API_KEY is not set; this suite calls Groq (set the key, or skip the suite)"


@dataclass
class Call:
    seconds: float
    prompt_tokens: int
    completion_tokens: int


@dataclass
class UsageRecorder:
    """Stands in for AsyncGroq: forwards chat completions and records each one."""

    client: Any
    calls: list[Call] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs: Any) -> Any:
        started = time.perf_counter()
        response = await self.client.chat.completions.create(**kwargs)
        usage = getattr(response, "usage", None)
        self.calls.append(Call(
            seconds=time.perf_counter() - started,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        ))
        return response

    async def close(self) -> None:
        await self.client.close()


def groq_configured() -> bool:
    from config import settings

    return settings.has_groq_key and not settings.MOCK_LLM


@contextlib.asynccontextmanager
async def groq_only() -> AsyncIterator[UsageRecorder]:
    """Route the application's LLM calls to Groq alone, through a UsageRecorder.

    OpenAI is switched off for the duration so the measured provider is the
    deployed one even when OPENAI_API_KEY is also set.
    """
    from config import settings
    from services import llm

    saved = (settings.OPENAI_API_KEY, llm._groq_client)
    recorder = UsageRecorder(llm._create_groq_client())
    settings.OPENAI_API_KEY = None
    llm._groq_client = recorder
    try:
        yield recorder
    finally:
        settings.OPENAI_API_KEY, llm._groq_client = saved
        await recorder.close()


@contextlib.contextmanager
def no_llm() -> Iterator[None]:
    """Disable every provider (and mock mode), so AI steps report "not configured"."""
    from config import settings

    saved = (settings.GROQ_API_KEY, settings.OPENAI_API_KEY, settings.MOCK_LLM)
    settings.GROQ_API_KEY = settings.OPENAI_API_KEY = None
    settings.MOCK_LLM = False
    try:
        yield
    finally:
        settings.GROQ_API_KEY, settings.OPENAI_API_KEY, settings.MOCK_LLM = saved


def _rate_limited(exc: Exception) -> bool:
    from services.llm import LLMProviderError

    return isinstance(exc, LLMProviderError) and "rate limiting" in exc.detail


async def with_retries[T](call: Callable[[], Awaitable[T]]) -> T:
    """Run call(), waiting and retrying while the provider reports rate limiting."""
    for attempt in range(eval_settings.RATE_LIMIT_RETRIES + 1):
        try:
            return await call()
        except Exception as exc:
            if not _rate_limited(exc) or attempt == eval_settings.RATE_LIMIT_RETRIES:
                raise
            delay = eval_settings.RATE_LIMIT_BACKOFF_SECONDS * (attempt + 1)
            logger.warning("Rate limited; retrying in %.0fs", delay)
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


def usage_summary(calls: list[Call], items: int) -> dict[str, Any]:
    """Token totals per item and the estimated cost at the configured Groq prices."""
    prompt = sum(call.prompt_tokens for call in calls)
    completion = sum(call.completion_tokens for call in calls)
    cost = eval_settings.cost_usd(prompt, completion)
    return {
        "requests": len(calls),
        "prompt_tokens_per_item": round(prompt / items, 1) if items else 0,
        "completion_tokens_per_item": round(completion / items, 1) if items else 0,
        "cost_usd_per_item": round(cost / items, 6) if items else 0,
        "cost_usd_total": round(cost, 4),
        "price_usd_per_mtok": {"input": eval_settings.GROQ_INPUT_USD_PER_MTOK,
                               "output": eval_settings.GROQ_OUTPUT_USD_PER_MTOK},
    }
