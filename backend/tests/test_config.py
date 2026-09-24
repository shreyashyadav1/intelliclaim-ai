"""Tests for application settings parsing."""

import re

import pytest
from pydantic import ValidationError

from config import BACKEND_DIR, Settings

ENV_EXAMPLE = BACKEND_DIR.parent / ".env.example"


def _settings(**env) -> Settings:
    # _env_file=None keeps a developer's backend/.env out of these tests.
    return Settings(_env_file=None, **env)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://a.example.com,https://b.example.com", ["https://a.example.com", "https://b.example.com"]),
        (" https://a.example.com/ , http://localhost:5173 ", ["https://a.example.com", "http://localhost:5173"]),
        ('["https://a.example.com", "http://localhost:5173"]', ["https://a.example.com", "http://localhost:5173"]),
        ("https://only.example.com", ["https://only.example.com"]),
        ("", []),
    ],
)
def test_allowed_origins_accepts_csv_and_json(monkeypatch, raw, expected):
    monkeypatch.setenv("ALLOWED_ORIGINS", raw)
    assert _settings().ALLOWED_ORIGINS == expected


def test_allowed_origins_rejects_malformed_json(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", '["https://a.example.com",')
    with pytest.raises(ValidationError):
        _settings()


def test_allowed_origins_default_includes_production_frontend(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert "https://intelliclaim-ai.vercel.app" in _settings().ALLOWED_ORIGINS


def test_blank_api_keys_count_as_unset(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "   ")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    settings = _settings()
    assert settings.GROQ_API_KEY is None
    assert settings.has_groq_key is False
    assert settings.has_openai_key is False


def test_env_example_lists_exactly_the_settings_fields():
    """.env.example is the reference for operators, so it must not drift from Settings."""
    keys = set()
    for line in ENV_EXAMPLE.read_text().splitlines():
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", line.strip())
        if match:
            keys.add(match.group(1))
    assert keys == set(Settings.model_fields)
