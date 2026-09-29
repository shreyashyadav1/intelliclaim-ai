"""
Evaluation settings, read from EVAL_* environment variables (or backend/.env).

They configure the harness only; the application's own settings stay in
config.py. Provider keys (GROQ_API_KEY, OPENAI_API_KEY) are the
application's.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from config import BACKEND_DIR


class EvalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="EVAL_", env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Groq on-demand list price for llama-3.3-70b-versatile in USD per million tokens.
    # Source: https://groq.com/pricing (0.59 input / 0.79 output as last published there).
    # Check the current price and override these when it or GROQ_MODEL changes.
    GROQ_INPUT_USD_PER_MTOK: float = Field(default=0.59, ge=0)
    GROQ_OUTPUT_USD_PER_MTOK: float = Field(default=0.79, ge=0)

    # MongoDB for the risk suite's duplicate check; a throwaway database is created and dropped.
    # Falls back to TEST_MONGODB_URI, then mongodb://localhost:27017.
    MONGODB_URI: str | None = None

    # Retries (with backoff) when the provider rate-limits the LLM suites.
    RATE_LIMIT_RETRIES: int = Field(default=6, ge=0)
    RATE_LIMIT_BACKOFF_SECONDS: float = Field(default=10.0, ge=0)

    def cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.GROQ_INPUT_USD_PER_MTOK + completion_tokens * self.GROQ_OUTPUT_USD_PER_MTOK) / 1e6


eval_settings = EvalSettings()
