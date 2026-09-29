"""
IntelliClaim AI - Configuration Module

Settings come from environment variables and, for local development, from
backend/.env. Environment variables win over the file. Every setting is
listed in the repository's .env.example.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class GenerationParams:
    """Sampling parameters for one kind of LLM call."""

    temperature: float
    max_tokens: int


# Per-task generation parameters, shared by every provider.
EXTRACTION_PARAMS = GenerationParams(temperature=0.0, max_tokens=1024)
VALIDATION_PARAMS = GenerationParams(temperature=0.2, max_tokens=1024)
RAG_ANSWER_PARAMS = GenerationParams(temperature=0.1, max_tokens=500)
CLASSIFICATION_PARAMS = GenerationParams(temperature=0.0, max_tokens=20)
HEALTH_CHECK_PARAMS = GenerationParams(temperature=0.0, max_tokens=10)

# Embedding models. Vectors from different models are not comparable, so
# changing either one requires re-indexing (POST /api/rag/index-all).
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"  # fastembed, local ONNX
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI path only


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # AI providers
    GROQ_API_KEY: str | None = Field(default=None, description="Groq API key")
    GROQ_MODEL: str = Field(default="llama-3.3-70b-versatile", description="Groq chat model")
    OPENAI_API_KEY: str | None = Field(
        default=None, description="OpenAI API key; when set, OpenAI is tried before Groq"
    )
    OPENAI_MODEL: str = Field(default="gpt-4o", description="OpenAI chat model")
    LLM_TIMEOUT_SECONDS: float = Field(default=20.0, gt=0, description="Per-request timeout for AI providers")
    LLM_MAX_RETRIES: int = Field(default=1, ge=0, le=5, description="Retries for failed AI provider requests")
    MOCK_LLM: bool = Field(
        default=False,
        description="Return clearly labelled mock AI output instead of calling a provider (demos and tests)",
    )
    EXTRACTION_MAX_INPUT_CHARS: int = Field(
        default=4000, ge=500, description="Characters of document text sent to the model for extraction"
    )

    # MongoDB
    MONGODB_URI: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URI")
    MONGODB_DB_NAME: str = Field(default="intelliclaim", description="MongoDB database name")

    # File storage and uploads
    LOCAL_STORAGE_PATH: str = Field(
        default="./uploads", description="Directory for uploaded files (relative to the working directory, or absolute)"
    )
    MAX_UPLOAD_MB: int = Field(default=50, ge=1, description="Largest accepted upload, in MB")

    # Vector search
    CHROMA_PERSIST_DIR: str = Field(default="./chroma_data", description="ChromaDB persistence directory")
    FASTEMBED_CACHE_PATH: str | None = Field(
        default=None, description="Directory holding the fastembed model files (the Docker image pre-downloads them)"
    )

    # CORS: accepts a comma-separated string or a JSON array.
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default=[
            "http://localhost:5173",
            "http://localhost:5177",
            "http://127.0.0.1:5173",
            "https://intelliclaim-ai.vercel.app",
        ],
        description="Allowed CORS origins",
    )

    @field_validator("GROQ_API_KEY", "OPENAI_API_KEY", "FASTEMBED_CACHE_PATH", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        """Treat empty or whitespace-only values (e.g. `GROQ_API_KEY=`) as unset."""
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    value = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError("ALLOWED_ORIGINS is not a valid JSON array") from exc
            else:
                value = text.split(",")
        if isinstance(value, list | tuple):
            # Browsers send origins without a trailing slash, so normalise it away.
            return [str(origin).strip().rstrip("/") for origin in value if str(origin).strip()]
        return value

    @property
    def has_openai_key(self) -> bool:
        """Check if OpenAI API key is configured."""
        return bool(self.OPENAI_API_KEY and self.OPENAI_API_KEY.strip())

    @property
    def has_groq_key(self) -> bool:
        """Check if Groq API key is configured."""
        return bool(self.GROQ_API_KEY and self.GROQ_API_KEY.strip())

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def llm_configured(self) -> bool:
        """True when at least one real AI provider has an API key."""
        return self.has_openai_key or self.has_groq_key

    @property
    def ai_provider(self) -> str:
        """The provider that AI features use first: mock, openai, groq or none."""
        if self.MOCK_LLM:
            return "mock"
        if self.has_openai_key:
            return "openai"
        if self.has_groq_key:
            return "groq"
        return "none"


settings = Settings()
