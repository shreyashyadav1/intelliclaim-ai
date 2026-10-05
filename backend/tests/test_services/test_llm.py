"""Tests for the shared LLM client helpers."""

import groq
import openai
import pytest

from config import EXTRACTION_PARAMS, settings
from services import llm


def test_groq_client_requires_a_key():
    with pytest.raises(llm.LLMNotConfiguredError) as excinfo:
        llm.get_groq_client()
    assert excinfo.value.status_code == 503


def test_groq_client_is_created_once_and_reused(monkeypatch):
    created = []

    class _Client:
        async def close(self):
            pass

    def _factory():
        created.append(_Client())
        return created[-1]

    monkeypatch.setattr(settings, "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_create_groq_client", _factory)

    first = llm.get_groq_client()
    second = llm.get_groq_client()
    assert first is second
    assert len(created) == 1


@pytest.mark.parametrize(
    ("factory_name", "sdk", "class_name", "key_setting"),
    [("groq", groq, "AsyncGroq", "GROQ_API_KEY"), ("openai", openai, "AsyncOpenAI", "OPENAI_API_KEY")],
)
def test_client_factories_use_settings(monkeypatch, ai_client_guard, factory_name, sdk, class_name, key_setting):
    """The real factories pass the configured key, timeout and retry count to the SDK."""
    captured = {}

    class _Recorder:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(sdk, class_name, _Recorder)
    monkeypatch.setattr(settings, key_setting, "test-key")
    monkeypatch.setattr(settings, "LLM_TIMEOUT_SECONDS", 7.5)
    monkeypatch.setattr(settings, "LLM_MAX_RETRIES", 3)

    getattr(ai_client_guard, factory_name)()

    assert captured == {"api_key": "test-key", "timeout": 7.5, "max_retries": 3}


def test_configured_providers_order(monkeypatch):
    assert llm.configured_providers() == []
    monkeypatch.setattr(settings, "GROQ_API_KEY", "g")
    assert llm.configured_providers() == ["groq"]
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "o")
    assert llm.configured_providers() == ["openai", "groq"]


async def test_groq_chat_uses_configured_model_and_params(fake_groq, monkeypatch):
    monkeypatch.setattr(settings, "GROQ_MODEL", "test-model")
    fake_groq.respond('{"ok": true}')

    content = await llm.groq_chat([{"role": "user", "content": "json please"}], EXTRACTION_PARAMS, json_mode=True)

    assert content == '{"ok": true}'
    call = fake_groq.calls[0]
    assert call["model"] == "test-model"
    assert call["temperature"] == EXTRACTION_PARAMS.temperature
    assert call["max_tokens"] == EXTRACTION_PARAMS.max_tokens
    assert call["response_format"] == {"type": "json_object"}


async def test_groq_chat_without_json_mode_omits_response_format(fake_groq):
    fake_groq.respond("plain text")
    await llm.groq_chat([{"role": "user", "content": "hi"}], EXTRACTION_PARAMS)
    assert "response_format" not in fake_groq.calls[0]


def test_default_groq_model_is_a_supported_reasoning_model():
    # llama-3.3-70b-versatile was shut down for free and developer tiers on 2026-08-16.
    assert settings.model_fields["GROQ_MODEL"].default == "openai/gpt-oss-120b"
    assert settings.model_fields["GROQ_REASONING_EFFORT"].default == "low"


async def test_groq_chat_sends_the_configured_reasoning_effort(fake_groq, monkeypatch):
    monkeypatch.setattr(settings, "GROQ_REASONING_EFFORT", "medium")
    fake_groq.respond("ok")
    await llm.groq_chat([{"role": "user", "content": "hi"}], EXTRACTION_PARAMS)
    assert fake_groq.calls[0]["reasoning_effort"] == "medium"


async def test_groq_chat_omits_reasoning_effort_when_blank(fake_groq, monkeypatch):
    # Models without reasoning support reject the parameter.
    monkeypatch.setattr(settings, "GROQ_REASONING_EFFORT", "")
    fake_groq.respond("ok")
    await llm.groq_chat([{"role": "user", "content": "hi"}], EXTRACTION_PARAMS)
    assert "reasoning_effort" not in fake_groq.calls[0]


async def test_groq_failure_becomes_generic_provider_error(fake_groq, groq_errors):
    fake_groq.respond(groq_errors.connection())
    with pytest.raises(llm.LLMProviderError) as excinfo:
        await llm.groq_chat([{"role": "user", "content": "hi"}], EXTRACTION_PARAMS)
    assert excinfo.value.status_code == 502
    assert "Connection error" not in excinfo.value.detail


async def test_groq_rate_limit_has_a_specific_message(fake_groq, groq_errors):
    fake_groq.respond(groq_errors.rate_limit())
    with pytest.raises(llm.LLMProviderError) as excinfo:
        await llm.groq_chat([{"role": "user", "content": "hi"}], EXTRACTION_PARAMS)
    assert "rate limiting" in excinfo.value.detail


@pytest.mark.parametrize("content", ["", "   ", None])
async def test_empty_groq_reply_is_an_output_error(fake_groq, content):
    fake_groq.respond(content)
    with pytest.raises(llm.LLMOutputError):
        await llm.groq_chat([{"role": "user", "content": "hi"}], EXTRACTION_PARAMS)


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '"string"', None])
def test_parse_json_object_rejects_non_objects(raw):
    with pytest.raises(llm.LLMOutputError):
        llm.parse_json_object(raw)


def test_parse_json_object_accepts_objects():
    assert llm.parse_json_object('{"a": 1}') == {"a": 1}


async def test_close_clients_closes_and_forgets(fake_groq):
    closed = []

    async def _close():
        closed.append(True)

    fake_groq.close = _close
    await llm.close_clients()
    assert closed == [True]
    assert llm._groq_client is None
