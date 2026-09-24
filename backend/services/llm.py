"""
IntelliClaim AI - Shared LLM Clients

One AsyncGroq and one AsyncOpenAI client are created lazily and reused for
the lifetime of the process, so calls share a connection pool and never
block the event loop. Model names, timeouts and retries come from settings;
per-task sampling parameters come from config.GenerationParams.

Provider failures are raised as LLMError subclasses, which main.py turns
into {"detail": ...} responses: 503 when no provider is configured and 502
when a provider fails or returns unusable output.
"""

import json
import logging
from typing import Any

import groq
import openai

from config import GenerationParams, settings

logger = logging.getLogger("intelliclaim.llm")

Messages = list[dict[str, str]]


class LLMError(Exception):
    """Base class for AI provider errors. `detail` is safe to show to API clients."""

    status_code = 502
    default_detail = "The AI provider request failed. Please try again later."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class LLMNotConfiguredError(LLMError):
    status_code = 503
    default_detail = (
        "No AI provider is configured. Set GROQ_API_KEY or OPENAI_API_KEY, "
        "or MOCK_LLM=true for labelled demo output."
    )


class LLMProviderError(LLMError):
    """The provider could not be reached or rejected the request."""


class LLMOutputError(LLMError):
    """The provider answered, but not with output the application can use."""

    default_detail = "The AI provider returned an invalid response. Please try again."


_RATE_LIMITED_DETAIL = "The AI provider is rate limiting requests. Please try again in a minute."

_groq_client: groq.AsyncGroq | None = None
_openai_client: openai.AsyncOpenAI | None = None


def _create_groq_client() -> groq.AsyncGroq:
    return groq.AsyncGroq(
        api_key=settings.GROQ_API_KEY,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )


def _create_openai_client() -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=settings.LLM_MAX_RETRIES,
    )


def get_groq_client() -> groq.AsyncGroq:
    """Return the shared AsyncGroq client, creating it on first use."""
    global _groq_client
    if not settings.has_groq_key:
        raise LLMNotConfiguredError("Groq is not configured: GROQ_API_KEY is not set.")
    if _groq_client is None:
        _groq_client = _create_groq_client()
    return _groq_client


def get_openai_client() -> openai.AsyncOpenAI:
    """Return the shared AsyncOpenAI client, creating it on first use."""
    global _openai_client
    if not settings.has_openai_key:
        raise LLMNotConfiguredError("OpenAI is not configured: OPENAI_API_KEY is not set.")
    if _openai_client is None:
        _openai_client = _create_openai_client()
    return _openai_client


async def close_clients() -> None:
    """Close the shared clients (called on application shutdown)."""
    global _groq_client, _openai_client
    for client in (_groq_client, _openai_client):
        if client is not None:
            await client.close()
    _groq_client = None
    _openai_client = None


def configured_providers() -> list[str]:
    """Providers with an API key, in the order they are tried."""
    providers = []
    if settings.has_openai_key:
        providers.append("openai")
    if settings.has_groq_key:
        providers.append("groq")
    return providers


def parse_json_object(raw: str | None) -> dict[str, Any]:
    """Parse model output that must be a JSON object."""
    try:
        data = json.loads(raw or "")
    except (TypeError, ValueError) as exc:
        raise LLMOutputError() from exc
    if not isinstance(data, dict):
        raise LLMOutputError()
    return data


def _message_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError):
        content = None
    if not isinstance(content, str) or not content.strip():
        raise LLMOutputError()
    return content


async def groq_chat(messages: Messages, params: GenerationParams, *, json_mode: bool = False) -> str:
    """Run a Groq chat completion and return the message text."""
    client = get_groq_client()
    extra: dict[str, Any] = {"response_format": {"type": "json_object"}} if json_mode else {}
    try:
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=messages,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
            **extra,
        )
    except groq.RateLimitError as exc:
        logger.warning("Groq rate limit reached: %s", exc)
        raise LLMProviderError(_RATE_LIMITED_DETAIL) from exc
    except groq.APIError as exc:
        logger.warning("Groq request failed (%s): %s", type(exc).__name__, exc)
        raise LLMProviderError() from exc
    return _message_content(response)


async def openai_chat(messages: Messages, params: GenerationParams) -> str:
    """Run an OpenAI chat completion and return the message text."""
    client = get_openai_client()
    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
        )
    except openai.RateLimitError as exc:
        logger.warning("OpenAI rate limit reached: %s", exc)
        raise LLMProviderError(_RATE_LIMITED_DETAIL) from exc
    except openai.APIError as exc:
        logger.warning("OpenAI request failed (%s): %s", type(exc).__name__, exc)
        raise LLMProviderError() from exc
    return _message_content(response)


async def openai_tool_call(messages: Messages, params: GenerationParams, tool: dict[str, Any]) -> dict[str, Any]:
    """Force a single OpenAI function call and return its parsed arguments."""
    client = get_openai_client()
    name = tool["function"]["name"]
    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": name}},
            temperature=params.temperature,
            max_tokens=params.max_tokens,
        )
    except openai.RateLimitError as exc:
        logger.warning("OpenAI rate limit reached: %s", exc)
        raise LLMProviderError(_RATE_LIMITED_DETAIL) from exc
    except openai.APIError as exc:
        logger.warning("OpenAI request failed (%s): %s", type(exc).__name__, exc)
        raise LLMProviderError() from exc

    try:
        arguments = response.choices[0].message.tool_calls[0].function.arguments
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMOutputError() from exc
    return parse_json_object(arguments)
