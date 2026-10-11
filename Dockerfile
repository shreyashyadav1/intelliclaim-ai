# IntelliClaim AI backend image, used by Railway and by docker compose.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    LOCAL_STORAGE_PATH=/app/uploads \
    CHROMA_PERSIST_DIR=/app/chroma_data

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# Bake the embedding model into the image so the first search after a deploy or
# restart does not download it. Must match config.EMBEDDING_MODEL_NAME.
ARG FASTEMBED_MODEL=BAAI/bge-small-en-v1.5
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='${FASTEMBED_MODEL}', cache_dir='${FASTEMBED_CACHE_PATH}')" \
    && chown -R app:app "${FASTEMBED_CACHE_PATH}"

COPY --chown=app:app backend/ .
RUN mkdir -p /app/uploads /app/chroma_data && chown app:app /app/uploads /app/chroma_data

USER app

EXPOSE 8000

# /api/health returns 503 when MongoDB is unreachable, which marks the container unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'), timeout=4)" || exit 1

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
