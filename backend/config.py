"""
IntelliClaim AI - Configuration Module

Settings come from environment variables and, for local development, from
backend/.env. Environment variables win over the file. Every setting is
listed in the repository's .env.example.
"""

import json
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent


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
    OPENAI_API_KEY: str | None = Field(
        default=None, description="OpenAI API key; when set, OpenAI is tried before Groq"
    )

    # MongoDB
    MONGODB_URI: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URI")
    MONGODB_DB_NAME: str = Field(default="intelliclaim", description="MongoDB database name")

    # File storage
    LOCAL_STORAGE_PATH: str = Field(default="./uploads", description="Directory for uploaded files")

    # ChromaDB
    CHROMA_PERSIST_DIR: str = Field(default="./chroma_data", description="ChromaDB persistence directory")

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

    @field_validator("GROQ_API_KEY", "OPENAI_API_KEY", mode="before")
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


settings = Settings()
