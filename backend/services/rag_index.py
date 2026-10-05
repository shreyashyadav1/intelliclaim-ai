"""
IntelliClaim AI - Vector index: LlamaIndex ingestion, LangChain retrieval

Every document chunk lives in one ChromaDB collection:

- Ingestion (LlamaIndex): each page becomes a Document tagged with filename,
  document_class and page (LlamaIndex adds document_id). SentenceSplitter
  cuts pages into chunks, the fastembed model embeds them and
  ChromaVectorStore writes them to the collection.
- Retrieval (LangChain): a Chroma vector store over the same collection,
  with LangChain embeddings wrapping the same fastembed model, answers
  cosine-similarity searches. Hybrid mode fuses those results with BM25
  keyword search over the stored chunks (rank_bm25's BM25Okapi behind a
  LangChain retriever; EnsembleRetriever, weighted reciprocal rank fusion).

One fastembed model (BAAI/bge-small-en-v1.5) serves both frameworks, so
documents and questions are embedded identically and the ONNX model is
loaded only once per process.

The LangChain adapters for fastembed and BM25 are defined here on top of
langchain-core: langchain-community, which provided them, is no longer
maintained, and neither has a standalone integration package.
"""

import asyncio
import logging
import re
import threading
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document as LCDocument
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from llama_index.core import Document
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from pydantic import ConfigDict, Field
from rank_bm25 import BM25Okapi

from config import (
    EMBEDDING_MODEL_NAME,
    HYBRID_CANDIDATES,
    HYBRID_WEIGHTS,
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RRF_K,
)
from services.rag_errors import IncompatibleIndexError
from utils.paged_text import split_pages

logger = logging.getLogger(__name__)

RETRIEVAL_MODES = ("vector", "hybrid")

# Collections created by this module record the embedding model that filled them.
COLLECTION_METADATA = {"hnsw:space": "cosine", "embedding_model": EMBEDDING_MODEL_NAME}

# Metadata keys LlamaIndex manages itself; values supplied by callers are dropped.
_MANAGED_KEYS = frozenset({"doc_id", "document_id", "ref_doc_id", "page"})


# ---------------------------------------------------------------------------
# Embeddings: one fastembed model behind both frameworks' interfaces
# ---------------------------------------------------------------------------
class SharedFastEmbedEmbedding(BaseEmbedding):
    """LlamaIndex embedding backed by an already loaded fastembed TextEmbedding.

    Behaves like FastEmbedEmbedding from llama-index-embeddings-fastembed,
    which cannot be used here: its package metadata requires Python < 3.13,
    and it always loads its own copy of the ONNX model.
    """

    _model: Any = PrivateAttr()

    def __init__(self, model: Any, **kwargs: Any) -> None:
        super().__init__(model_name=EMBEDDING_MODEL_NAME, embed_batch_size=64, **kwargs)
        self._model = model

    @classmethod
    def class_name(cls) -> str:
        return "SharedFastEmbedEmbedding"

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._get_text_embeddings([text])[0]

    def _get_query_embedding(self, query: str) -> list[float]:
        return next(iter(self._model.query_embed(query))).tolist()

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return await asyncio.to_thread(self._get_query_embedding, query)

    async def _aget_text_embedding(self, text: str) -> list[float]:
        return await asyncio.to_thread(self._get_text_embedding, text)


class SharedFastEmbedEmbeddings(Embeddings):
    """LangChain embeddings backed by an already loaded fastembed TextEmbedding.

    The LangChain counterpart of SharedFastEmbedEmbedding. It calls fastembed
    exactly as langchain-community's FastEmbedEmbeddings did with its
    defaults (batches of 256, no data-parallel workers), so the vectors are
    the same.
    """

    BATCH_SIZE = 256

    def __init__(self, model: Any) -> None:
        self.model = model
        self.model_name = EMBEDDING_MODEL_NAME

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.embed(texts, batch_size=self.BATCH_SIZE, parallel=None)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self.model.query_embed(text, batch_size=self.BATCH_SIZE, parallel=None))).tolist()


def langchain_embeddings(model: Any) -> SharedFastEmbedEmbeddings:
    """LangChain embeddings around an already loaded fastembed model (no second copy is loaded)."""
    return SharedFastEmbedEmbeddings(model)


# ---------------------------------------------------------------------------
# Retrievers
# ---------------------------------------------------------------------------
_TOKEN = re.compile(r"[a-z0-9]+(?:[-./][a-z0-9]+)*")
_TOKEN_PARTS = re.compile(r"[-./]")


def keyword_tokens(text: str) -> list[str]:
    """BM25 tokens: lower-cased words and identifiers, plus the parts of identifiers.

    "Invoice INV-1043" -> ["invoice", "inv-1043", "inv", "1043"], so a question
    matches both the full identifier and its number.
    """
    tokens: list[str] = []
    for token in _TOKEN.findall(text.lower()):
        tokens.append(token)
        parts = _TOKEN_PARTS.split(token)
        if len(parts) > 1:
            tokens.extend(part for part in parts if part)
    return tokens


def _as_result(doc: LCDocument, **extra: Any) -> LCDocument:
    """Copy a stored chunk for a result list, dropping LlamaIndex's internal metadata."""
    metadata = {key: value for key, value in doc.metadata.items() if not key.startswith("_")}
    return LCDocument(page_content=doc.page_content, metadata={**metadata, "chunk_id": doc.id, **extra}, id=doc.id)


class VectorRetriever(BaseRetriever):
    """Cosine-similarity search through LangChain's Chroma vector store.

    Each result carries metadata["score"]: the cosine similarity (1 - cosine distance).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vectorstore: Chroma
    k: int = 5

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[LCDocument]:
        results = self.vectorstore.similarity_search_with_score(query, k=self.k)
        return [_as_result(doc, score=1.0 - distance) for doc, distance in results]


class KeywordRetriever(BaseRetriever):
    """BM25 (rank_bm25's BM25Okapi, default parameters) over the indexed chunks.

    Chunks that share no term with the query are dropped: langchain-community's
    BM25Retriever returned k chunks even when none of them matched, which
    would feed arbitrary chunks into the fusion. Overlap is checked on the
    terms themselves: in small corpora BM25Okapi can score a real match 0.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vectorizer: Any
    docs: list[LCDocument] = Field(repr=False)
    k: int = 4
    preprocess_func: Callable[[str], list[str]] = keyword_tokens

    @classmethod
    def from_documents(
        cls, documents: Sequence[LCDocument], *, preprocess_func: Callable[[str], list[str]] = keyword_tokens,
        **kwargs: Any,
    ) -> "KeywordRetriever":
        """Index the documents' text with BM25Okapi; kwargs set the other fields (e.g. k)."""
        docs = list(documents)
        vectorizer = BM25Okapi([preprocess_func(doc.page_content) for doc in docs])
        return cls(vectorizer=vectorizer, docs=docs, preprocess_func=preprocess_func, **kwargs)

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[LCDocument]:
        terms = set(self.preprocess_func(query))
        scores = self.vectorizer.get_scores(list(terms))
        matching = [i for i, freqs in enumerate(self.vectorizer.doc_freqs) if not terms.isdisjoint(freqs)]
        ranked = sorted(matching, key=lambda i: (-scores[i], i))
        return [_as_result(self.docs[i], bm25_score=float(scores[i])) for i in ranked[: self.k]]


class HybridRetriever(BaseRetriever):
    """Vector + BM25 results fused by weighted reciprocal rank fusion, cut to k.

    metadata["score"] stays the cosine similarity for every result (the API
    reports it as the match percentage); chunks found only by BM25 get theirs
    from fill_scores.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ensemble: EnsembleRetriever
    k: int = 5
    fill_scores: Callable[[str, list[LCDocument]], None] | None = None

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[LCDocument]:
        docs = self.ensemble.invoke(query, config={"callbacks": run_manager.get_child()})[: self.k]
        if self.fill_scores is not None:
            self.fill_scores(query, docs)
        return docs


def hybrid_retriever(
    vector: BaseRetriever,
    keyword: BaseRetriever,
    k: int,
    *,
    weights: Sequence[float] = HYBRID_WEIGHTS,
    fill_scores: Callable[[str, list[LCDocument]], None] | None = None,
) -> HybridRetriever:
    """Fuse two retrievers whose results carry metadata["chunk_id"]."""
    ensemble = EnsembleRetriever(retrievers=[vector, keyword], weights=list(weights), c=RRF_K, id_key="chunk_id")
    return HybridRetriever(ensemble=ensemble, k=k, fill_scores=fill_scores)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denominator) if denominator else 0.0


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------
def _chunk_id(index: int, document: Document) -> str:
    """Deterministic chunk ids: <document id>:p<page>:<chunk number within the page>."""
    return f"{document.id_}:p{document.metadata.get('page', 0)}:{index}"


def page_documents(doc_id: str, text: str, metadata: dict[str, Any], page_starts: object = None) -> list[Document]:
    """One LlamaIndex Document per page with text, tagged with the page number when known.

    Metadata is stored with every chunk but kept out of the text that is
    embedded or sent to the model, so chunk sizes measure document text only.
    """
    base = {
        key: value for key, value in metadata.items() if value is not None and key not in _MANAGED_KEYS
    }
    documents = []
    for page, page_text in split_pages(text, page_starts):
        page_metadata = {**base, "page": page} if page is not None else dict(base)
        documents.append(
            Document(
                text=page_text,
                id_=doc_id,  # LlamaIndex writes it to document_id/doc_id/ref_doc_id on every chunk
                metadata=page_metadata,
                excluded_embed_metadata_keys=list(page_metadata),
                excluded_llm_metadata_keys=list(page_metadata),
            )
        )
    return documents


class VectorIndex:
    """One Chroma collection with the ingestion and retrieval pipelines over it.

    embedder_factory returns the fastembed model; it is called on first use,
    so deleting or counting chunks never loads the model. Methods block
    (embedding and Chroma calls), so async callers run them in a worker thread.
    """

    def __init__(
        self,
        client: Any,
        collection: Any,
        embedder_factory: Callable[[], Any],
        *,
        chunk_size: int = RAG_CHUNK_SIZE,
        chunk_overlap: int = RAG_CHUNK_OVERLAP,
    ) -> None:
        self.client = client
        self.collection = collection
        self.embedder_factory = embedder_factory
        self.chunk_size = chunk_size
        self._splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, id_func=_chunk_id)
        self._embedder: Any = None
        self._embed_model: SharedFastEmbedEmbedding | None = None
        self._embeddings: SharedFastEmbedEmbeddings | None = None
        self._vectorstore: Chroma | None = None
        self._dimension: int | None = None
        self._model_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._revision = 0  # bumped on every write; invalidates the BM25 corpus
        self._keyword_lock = threading.Lock()
        self._keyword_cache: tuple[int, KeywordRetriever | None] | None = None

    def _load_embedder(self) -> None:
        with self._model_lock:
            if self._embedder is None:
                embedder = self.embedder_factory()
                self._embed_model = SharedFastEmbedEmbedding(embedder)
                self._embeddings = langchain_embeddings(embedder)
                self._embedder = embedder

    @property
    def embed_model(self) -> SharedFastEmbedEmbedding:
        """LlamaIndex view of the embedding model (ingestion)."""
        if self._embed_model is None:
            self._load_embedder()
        return self._embed_model  # type: ignore[return-value]

    @property
    def embeddings(self) -> SharedFastEmbedEmbeddings:
        """LangChain view of the same embedding model (retrieval)."""
        if self._embeddings is None:
            self._load_embedder()
        return self._embeddings  # type: ignore[return-value]

    # ---------------------------------------------------------------- ingestion
    def add_document(self, doc_id: str, text: str, metadata: dict[str, Any], page_starts: object = None) -> int:
        """Chunk, embed and store a document, replacing its previous chunks. Returns the chunk count."""
        documents = page_documents(doc_id, text, metadata, page_starts)
        if not documents:
            return 0

        # Pages are split one at a time: the splitter looks parents up by id, and every
        # page shares the document's id so that chunks carry it as document_id.
        chunks = [chunk for page in documents for chunk in self._splitter.get_nodes_from_documents([page])]
        # Embed before touching the collection, so a failure leaves the previous vectors in place.
        nodes = IngestionPipeline(transformations=[self.embed_model], disable_cache=True).run(nodes=chunks)
        if not nodes:
            return 0
        self.check_compatible(dimension=len(nodes[0].get_embedding()))

        with self._write_lock:
            self.collection.delete(where={"doc_id": doc_id})
            ChromaVectorStore(chroma_collection=self.collection).add(nodes)
            self._revision += 1
        logger.info("Indexed document %s: %d chunks from %d page(s)", doc_id, len(nodes), len(documents))
        return len(nodes)

    def delete_document(self, doc_id: str) -> int:
        """Remove every chunk stored for a document; returns how many were removed."""
        with self._write_lock:
            ids = self.collection.get(where={"doc_id": doc_id}, include=[])["ids"]
            if ids:
                self.collection.delete(ids=ids)
                self._revision += 1
        return len(ids)

    def count(self) -> int:
        return self.collection.count()

    # ---------------------------------------------------------------- compatibility
    @property
    def dimension(self) -> int:
        """Vector size produced by the embedding model."""
        if self._dimension is None:
            self._dimension = len(self.embeddings.embed_query("dimension probe"))
        return self._dimension

    def stored_dimension(self) -> int | None:
        """Vector size of the chunks already in the collection (None when it is empty)."""
        stored = self.collection.get(limit=1, include=["embeddings"])
        if not stored["ids"]:
            return None
        return len(stored["embeddings"][0])

    def compatibility_problem(self, dimension: int | None = None) -> str | None:
        """Why the stored vectors cannot be compared with this model's (or `dimension`), or None."""
        recorded = (self.collection.metadata or {}).get("embedding_model")
        if recorded and recorded != EMBEDDING_MODEL_NAME:
            return f"model {recorded}"
        stored = self.stored_dimension()
        if stored is not None and stored != (dimension or self.dimension):
            return f"{stored}-dimensional vectors"
        return None

    def check_compatible(self, dimension: int | None = None) -> None:
        """Raise IncompatibleIndexError when the collection holds another model's vectors."""
        problem = self.compatibility_problem(dimension)
        if problem is not None:
            expected = f"{EMBEDDING_MODEL_NAME}, {dimension or self.dimension}-dimensional"
            raise IncompatibleIndexError(problem, expected)

    # ---------------------------------------------------------------- retrieval
    def retriever(self, mode: str, k: int, *, weights: Sequence[float] = HYBRID_WEIGHTS) -> BaseRetriever:
        """LangChain retriever returning up to k chunks: "vector" or "hybrid" (vector + BM25).

        weights are the (vector, BM25) weights of the rank fusion in hybrid mode.
        """
        if mode not in RETRIEVAL_MODES:
            raise ValueError(f"Unknown retrieval mode: {mode!r}")
        if mode == "vector":
            return VectorRetriever(vectorstore=self._langchain_store(), k=k)

        candidates = max(k, HYBRID_CANDIDATES)
        keyword = self._keyword_retriever(candidates)
        if keyword is None:  # nothing stored yet
            return VectorRetriever(vectorstore=self._langchain_store(), k=k)
        vector = VectorRetriever(vectorstore=self._langchain_store(), k=candidates)
        return hybrid_retriever(vector, keyword, k, weights=weights, fill_scores=self._fill_scores)

    def _langchain_store(self) -> Chroma:
        if self._vectorstore is None:
            self._vectorstore = Chroma(
                client=self.client,
                collection_name=self.collection.name,
                embedding_function=self.embeddings,
                create_collection_if_not_exists=False,
            )
        return self._vectorstore

    def _keyword_retriever(self, k: int) -> KeywordRetriever | None:
        """BM25 over every stored chunk, rebuilt only after the collection changes."""
        with self._keyword_lock:
            if self._keyword_cache is None or self._keyword_cache[0] != self._revision:
                revision = self._revision
                stored = self.collection.get(include=["documents", "metadatas"])
                corpus = [
                    LCDocument(page_content=text or "", metadata=metadata or {}, id=chunk_id)
                    for chunk_id, text, metadata in zip(
                        stored["ids"], stored["documents"], stored["metadatas"], strict=False
                    )
                ]
                retriever = (
                    KeywordRetriever.from_documents(corpus, preprocess_func=keyword_tokens) if corpus else None
                )
                self._keyword_cache = (revision, retriever)
            retriever = self._keyword_cache[1]
        return retriever.model_copy(update={"k": k}) if retriever is not None else None

    def _fill_scores(self, query: str, docs: list[LCDocument]) -> None:
        """Give chunks found only by BM25 their cosine similarity to the query."""
        missing = [doc for doc in docs if "score" not in doc.metadata]
        if not missing:
            return
        query_vector = np.asarray(self.embeddings.embed_query(query))
        stored = self.collection.get(ids=[doc.metadata["chunk_id"] for doc in missing], include=["embeddings"])
        vectors = dict(zip(stored["ids"], stored["embeddings"], strict=False))
        for doc in missing:
            vector = vectors.get(doc.metadata["chunk_id"])
            doc.metadata["score"] = _cosine(query_vector, np.asarray(vector)) if vector is not None else 0.0
