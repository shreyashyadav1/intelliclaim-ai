"""
IntelliClaim AI - Configuration Module

Loads application settings from environment variables and .env file.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenAI
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API key for GPT-4o")

    # MongoDB
    MONGODB_URI: str = Field(default="mongodb://localhost:27017", description="MongoDB connection URI")
    MONGODB_DB_NAME: str = Field(default="intelliclaim", description="MongoDB database name")

    # Storage
    STORAGE_TYPE: str = Field(default="local", description="Storage backend: local or s3")
    LOCAL_STORAGE_PATH: str = Field(default="./uploads", description="Local file storage path")

    # AWS S3 (optional)
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, description="AWS access key ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(default=None, description="AWS secret access key")
    AWS_REGION: Optional[str] = Field(default="us-east-1", description="AWS region")
    S3_BUCKET: Optional[str] = Field(default=None, description="S3 bucket name")

    # ChromaDB
    CHROMA_PERSIST_DIR: str = Field(default="./chroma_data", description="ChromaDB persistence directory")

    # CORS
    ALLOWED_ORIGINS: list[str] = Field(
        default=[
            "http://localhost:5173",
            "http://localhost:5177",
            "http://127.0.0.1:5173",
            "https://intelliclaim-ai.vercel.app",
        ],
        description="Allowed CORS origins",
    )

    # Server
    BACKEND_HOST: str = Field(default="0.0.0.0", description="Backend host")
    BACKEND_PORT: int = Field(default=8000, description="Backend port")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }

    @property
    def has_openai_key(self) -> bool:
        """Check if OpenAI API key is configured."""
        return self.OPENAI_API_KEY is not None and len(self.OPENAI_API_KEY) > 0


settings = Settings()
