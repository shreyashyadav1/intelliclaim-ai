"""
IntelliClaim AI - RAG (Retrieval-Augmented Generation) Service

Documents are indexed with LlamaIndex and questions are answered by a
LangChain LCEL chain, with whichever chat provider is configured:

- Ingestion (services.rag_index): pages -> SentenceSplitter chunks ->
  fastembed embeddings (BAAI/bge-small-en-v1.5, local ONNX) -> ChromaDB
  through ChromaVectorStore.
- Query (services.rag_chain): a LangChain retriever over the same collection
  (vector search, or vector + BM25 when RAG_RETRIEVAL_MODE=hybrid) ->
  numbered context -> ChatGroq (GROQ_MODEL) or ChatOpenAI -> an answer that
  cites its sources, returned with citations (document ids and filenames).

Indexing needs no LLM. Answering does: without a configured provider query()
raises LLMNotConfiguredError (HTTP 503). With MOCK_LLM=true retrieval is real
but the answer is a template labelled "source": "mock". A collection filled
by a different embedding model raises IncompatibleIndexError (HTTP 409)
until POST /api/rag/index-all rebuilds it.

LangChain, LlamaIndex and ChromaDB are imported on first use, which keeps
application startup light.
"""

import asyncio
import logging
import os
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from config import EMBEDDING_MODEL_NAME, RAG_ANSWER_PARAMS, settings
from services import llm
from services.llm import LLMNotConfiguredError
from services.rag_errors import VectorStoreUnavailableError

if TYPE_CHECKING:
    from langchain_core.documents import Document

    from services.rag_index import VectorIndex

logger = logging.getLogger(__name__)

COLLECTION_NAME = "intelliclaim_docs"

_NOT_INDEXED_ANSWER = "No documents have been indexed yet. Please upload and index some documents first."

# ---------------------------------------------------------------------------
# Lazy-initialised singletons for the vector store and the embedding model
# ---------------------------------------------------------------------------
_chroma_client = None
_chroma_collection = None
_embedder = None
_embedder_lock = threading.Lock()


def _collection_metadata() -> dict[str, str]:
    from services.rag_index import COLLECTION_METADATA

    return dict(COLLECTION_METADATA)


def _get_chroma_client():
    """Lazily initialise and return the ChromaDB persistent client."""
    global _chroma_client
    if _chroma_client is None:
        try:
            import chromadb
            os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
            _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            logger.info("ChromaDB client initialised at %s", settings.CHROMA_PERSIST_DIR)
        except Exception as e:
            logger.warning("Failed to initialise ChromaDB: %s", str(e))
            _chroma_client = None
    return _chroma_client


def _get_chroma_collection():
    """Return (or create) the 'intelliclaim_docs' ChromaDB collection."""
    global _chroma_collection
    if _chroma_collection is None:
        client = _get_chroma_client()
        if client is not None:
            # An existing collection keeps its metadata; only new ones record the embedding model.
            _chroma_collection = client.get_or_create_collection(name=COLLECTION_NAME, metadata=_collection_metadata())
    return _chroma_collection


def _require_collection():
    collection = _get_chroma_collection()
    if collection is None:
        raise VectorStoreUnavailableError("ChromaDB is unavailable")
    return collection


def _reset_collection():
    """Drop the collection and create an empty one for the current embedding model."""
    global _chroma_collection
    from chromadb.errors import NotFoundError

    client = _get_chroma_client()
    if client is None:
        raise VectorStoreUnavailableError("ChromaDB is unavailable")
    try:
        client.delete_collection(COLLECTION_NAME)
    except NotFoundError:
        pass
    _chroma_collection = client.create_collection(name=COLLECTION_NAME, metadata=_collection_metadata())
    return _chroma_collection


def _get_embedder():
    """Return the shared fastembed model, loading it on first use.

    Loading the ONNX model takes seconds and ~100 MB of memory, so it happens
    once per process; LlamaIndex (ingestion) and LangChain (retrieval) both use
    this instance. FASTEMBED_CACHE_PATH points at the copy baked into the
    Docker image, so production never downloads it at request time.
    """
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                from fastembed import TextEmbedding

                _embedder = TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=settings.FASTEMBED_CACHE_PATH)
                logger.info("Loaded fastembed model %s", EMBEDDING_MODEL_NAME)
    return _embedder


def _source(doc: "Document") -> dict[str, Any]:
    from services.rag_chain import document_id

    return {
        "doc_id": document_id(doc),
        "filename": doc.metadata.get("filename"),
        "text_snippet": doc.page_content[:200],
        "score": round(float(doc.metadata.get("score", 0.0)), 3),
        "page": doc.metadata.get("page"),
    }


def _model_error_logger():
    from langchain_core.callbacks import AsyncCallbackHandler

    class _LogModelErrors(AsyncCallbackHandler):
        """Logs each failed chat model call, including ones a fallback provider recovers from."""

        async def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
            logger.warning("RAG chat model call failed (%s): %s", type(error).__name__, error)

    return _LogModelErrors()


class RAGService:
    """Retrieval-Augmented Generation service for document Q&A.

    index_factory replaces the default index (the 'intelliclaim_docs'
    collection under CHROMA_PERSIST_DIR); the evaluation harness uses it to
    run the production query path over its own collection.
    """

    def __init__(self, index_factory: Callable[[], "VectorIndex"] | None = None) -> None:
        self._index_factory = index_factory
        self._index: VectorIndex | None = None
        self._index_lock = threading.Lock()

    def _vector_index(self) -> "VectorIndex":
        """The index over the current collection (blocking: opens ChromaDB on first use)."""
        if self._index_factory is not None:
            return self._index_factory()
        from services.rag_index import VectorIndex

        collection = _require_collection()
        with self._index_lock:
            index = self._index
            if index is None or index.collection is not collection or index.embedder_factory is not _get_embedder:
                index = self._index = VectorIndex(_get_chroma_client(), collection, _get_embedder)
        return index

    # ----------------------------------------------------------------
    # Document indexing
    # ----------------------------------------------------------------
    async def index_document(self, doc_id: str, text: str, metadata: dict, page_starts: object = None) -> int:
        """Index a document's text and return the number of chunks stored.

        page_starts (offsets of each page in text) tags chunks with their page.
        Existing vectors for the document are replaced, so re-indexing leaves
        no stale chunks behind.

        Raises:
            IncompatibleIndexError: the collection holds another embedding model's vectors.
        """
        if not text.strip():
            logger.warning("Skipping indexing for doc %s — empty text", doc_id)
            return 0
        return await asyncio.to_thread(
            lambda: self._vector_index().add_document(doc_id, text, metadata, page_starts)
        )

    async def delete_document(self, doc_id: str) -> int:
        """Remove every vector stored for a document; returns how many were removed."""
        removed = await asyncio.to_thread(lambda: self._vector_index().delete_document(doc_id))
        logger.info("Removed %d vectors for document %s", removed, doc_id)
        return removed

    async def reset_index(self) -> None:
        """Replace the collection with an empty one for the current embedding model.

        Used by POST /api/rag/index-all before re-indexing every document; it
        also clears vectors left by earlier embedding models or chunking.
        """

        def _reset() -> None:
            _get_embedder()  # fail before dropping anything if the model cannot load
            _reset_collection()
            with self._index_lock:
                self._index = None

        await asyncio.to_thread(_reset)
        logger.info("Search index reset (%s)", EMBEDDING_MODEL_NAME)

    # ----------------------------------------------------------------
    # Query
    # ----------------------------------------------------------------
    async def query(self, question: str, top_k: int = 5) -> dict[str, Any]:
        """Answer a natural-language question from the indexed documents.

        Returns a dict with 'answer', 'source_documents' (the retrieved chunks),
        'citations' (the documents the answer cites), 'source' ('openai',
        'groq', 'mock' or None when no model was needed) and 'retrieval_mode'.

        Raises:
            LLMNotConfiguredError: no provider is configured and MOCK_LLM is off.
            LLMProviderError / LLMOutputError: every configured provider failed.
            IncompatibleIndexError: the index must be rebuilt first.
        """
        from services import rag_chain

        mode = settings.RAG_RETRIEVAL_MODE
        answer_chain = self._answer_chain()

        index = await asyncio.to_thread(self._vector_index)
        if await asyncio.to_thread(index.count) == 0:
            return self._response(_NOT_INDEXED_ANSWER, [], None, mode)
        await asyncio.to_thread(index.check_compatible)

        retriever = await asyncio.to_thread(index.retriever, mode, top_k)
        chain = rag_chain.build_rag_chain(retriever, answer_chain)
        try:
            output = await chain.ainvoke(question, config={"callbacks": [_model_error_logger()], "run_name": "rag"})
        except Exception as exc:
            error = llm.as_llm_error(exc)
            if error is None:
                raise
            logger.warning("RAG answer failed: %s", error.detail)
            raise error from exc

        answer = output["answer"]
        logger.info("RAG answered via %s (%s retrieval): %s", answer["provider"], mode, question[:80])
        return self._response(answer["text"], output["docs"], answer["provider"], mode)

    @staticmethod
    def _answer_chain():
        """The answer step: mock template, or each configured provider in order."""
        from services import rag_chain

        if settings.MOCK_LLM:
            return rag_chain.mock_answer_chain()
        providers = llm.configured_providers()
        if not providers:
            raise LLMNotConfiguredError()
        chains = [
            rag_chain.build_answer_chain(llm.chat_model(provider, RAG_ANSWER_PARAMS), provider)
            for provider in providers
        ]
        return rag_chain.with_provider_fallbacks(chains)

    @staticmethod
    def _response(answer: str, docs: list, provider: str | None, mode: str) -> dict[str, Any]:
        from services.rag_chain import citations

        return {
            "answer": answer,
            "source_documents": [_source(doc) for doc in docs],
            "citations": citations(answer, docs),
            "source": "mock" if settings.MOCK_LLM else provider,
            "retrieval_mode": mode,
        }

    # ----------------------------------------------------------------
    # Stats
    # ----------------------------------------------------------------
    async def get_index_stats(self) -> dict[str, Any]:
        """Chunk count and status: ready, reindex_required, unavailable or error."""
        details = {"retrieval_mode": settings.RAG_RETRIEVAL_MODE, "embedding_model": EMBEDDING_MODEL_NAME}

        def _stats() -> dict[str, Any]:
            try:
                index = self._vector_index()
            except VectorStoreUnavailableError:
                return {"indexed_chunks": 0, "status": "unavailable"}
            count = index.count()
            status = "reindex_required" if count and index.compatibility_problem() else "ready"
            return {"indexed_chunks": count, "status": status}

        try:
            return {**await asyncio.to_thread(_stats), **details}
        except Exception:
            logger.exception("Failed to get index stats")
            return {"indexed_chunks": 0, "status": "error", **details}


# Module-level singleton
rag_service = RAGService()
