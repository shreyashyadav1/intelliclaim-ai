"""
IntelliClaim AI - FastAPI Application Entry Point

Main application module with CORS, router registration, and lifecycle events.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.connection import connect_db, close_db

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
    await close_db()
    logger.info("Database connection closed.")


app = FastAPI(
    title="IntelliClaim AI API",
    description="Insurance Document Intelligence Platform - AI-powered claim processing, extraction, RAG search, and risk detection.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and register routers
from routers import documents, claims, extraction, rag, analytics, validation

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
async def groq_test():
    """Test Groq API connectivity."""
    if not settings.has_groq_key:
        return {"status": "no_key"}
    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": 'Reply with this json exactly: {"ok": true}'}],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=10,
        )
        return {"status": "ok", "response": r.choices[0].message.content}
    except Exception as e:
        return {"status": "error", "error": str(e), "type": type(e).__name__}
