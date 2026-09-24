"""
IntelliClaim AI - FastAPI Application Entry Point

Main application module with CORS, router registration, and lifecycle events.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import HEALTH_CHECK_PARAMS, settings
from db.connection import close_db, connect_db
from routers import analytics, claims, documents, extraction, rag, validation
from services import llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("intelliclaim")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Starting IntelliClaim AI API...")
    await connect_db()
    logger.info("Database connected successfully.")
    yield
    logger.info("Shutting down IntelliClaim AI API...")
    await llm.close_clients()
    await close_db()
    logger.info("Database connection closed.")


app = FastAPI(
    title="IntelliClaim AI API",
    description=(
        "Insurance Document Intelligence Platform - AI-powered claim processing, "
        "extraction, RAG search, and risk detection."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(llm.LLMError)
async def llm_error_handler(request: Request, exc: llm.LLMError) -> JSONResponse:
    """503 when no AI provider is configured, 502 when the provider fails."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(documents.router, prefix="/api", tags=["Documents"])
app.include_router(claims.router, prefix="/api", tags=["Claims"])
app.include_router(extraction.router, prefix="/api", tags=["Extraction"])
app.include_router(rag.router, prefix="/api", tags=["RAG Search"])
app.include_router(analytics.router, prefix="/api", tags=["Analytics"])
app.include_router(validation.router, prefix="/api", tags=["Validation"])


@app.get("/api/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "IntelliClaim AI API",
        "version": "1.0.0",
        "openai_configured": settings.has_openai_key,
        "groq_configured": settings.has_groq_key,
        "ai_provider": "openai" if settings.has_openai_key else ("groq" if settings.has_groq_key else "none"),
    }


@app.get("/api/health/groq", tags=["System"])
async def groq_health():
    """Check Groq connectivity with a minimal JSON-mode completion."""
    if settings.MOCK_LLM:
        return {
            "status": "skipped",
            "source": "mock",
            "model": settings.GROQ_MODEL,
            "message": "MOCK_LLM is enabled, so Groq was not called.",
        }
    started = time.perf_counter()
    content = await llm.groq_chat(
        [{"role": "user", "content": 'Reply with this JSON exactly: {"ok": true}'}],
        HEALTH_CHECK_PARAMS,
        json_mode=True,
    )
    return {
        "status": "ok",
        "model": settings.GROQ_MODEL,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "response": content,
    }
