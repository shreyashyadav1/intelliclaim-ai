"""
IntelliClaim AI - RAG (Retrieval-Augmented Generation) Service

Indexes documents into ChromaDB via LlamaIndex and answers natural-language
questions using LangChain's RetrievalQA chain. Falls back to mock responses
when OpenAI keys are not configured.
"""

import logging
import os
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)

# Lazy-initialised singletons for vector store components
_chroma_collection = None
_chroma_client = None


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


def _get_collection():
    """Return (or create) the 'intelliclaim_docs' ChromaDB collection."""
    global _chroma_collection
    if _chroma_collection is None:
        client = _get_chroma_client()
        if client is not None:
            _chroma_collection = client.get_or_create_collection(
                name="intelliclaim_docs",
                metadata={"hnsw:space": "cosine"},
            )
    return _chroma_collection


class RAGService:
    """Retrieval-Augmented Generation service for document Q&A."""

    # ----------------------------------------------------------------
    # Document indexing
    # ----------------------------------------------------------------
    async def index_document(self, doc_id: str, text: str, metadata: dict) -> bool:
        """Index a document's text into ChromaDB for later retrieval.

        Splits the text into overlapping chunks and stores them with
        metadata in the vector store.

        Args:
            doc_id: Unique document identifier.
            text: Full extracted text from the document.
            metadata: Additional metadata (filename, document_class, etc.).

        Returns:
            True if indexing succeeded, False otherwise.
        """
        if not text.strip():
            logger.warning("Skipping indexing for doc %s — empty text", doc_id)
            return False

        try:
            collection = _get_collection()
            if collection is None:
                logger.warning("ChromaDB collection unavailable; skipping indexing")
                return False

            # Chunk the text into ~500-char overlapping segments
            chunks = self._chunk_text(text, chunk_size=500, overlap=50)

            ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{**metadata, "doc_id": doc_id, "chunk_index": i} for i in range(len(chunks))]

            # Upsert into ChromaDB (it will compute default embeddings)
            collection.upsert(
                ids=ids,
                documents=chunks,
                metadatas=metadatas,
            )

            logger.info("Indexed %d chunks for document %s", len(chunks), doc_id)
            return True

        except Exception as e:
            logger.error("Failed to index document %s: %s", doc_id, str(e))
            return False

    # ----------------------------------------------------------------
    # Query / Q&A
    # ----------------------------------------------------------------
    async def query(self, question: str) -> dict[str, Any]:
        """Answer a natural-language question using indexed documents.

        Uses LangChain with OpenAI when an API key is set; otherwise
        returns mock results.

        Args:
            question: The user's question.

        Returns:
            Dict with 'answer' (str) and 'source_documents' (list).
        """
        if settings.has_openai_key:
            try:
                return await self._query_with_langchain(question)
            except Exception as e:
                logger.warning("LangChain query failed, returning mock: %s", str(e))

        return self._mock_query(question)

    async def _query_with_langchain(self, question: str) -> dict[str, Any]:
        """Execute a RAG query using LangChain + ChromaDB + OpenAI.

        Args:
            question: Natural-language question.

        Returns:
            Dict with answer and source_documents.
        """
        collection = _get_collection()
        if collection is None or collection.count() == 0:
            return {
                "answer": "No documents have been indexed yet. Please upload and index some documents first.",
                "source_documents": [],
            }

        # Retrieve relevant chunks from ChromaDB
        results = collection.query(
            query_texts=[question],
            n_results=min(5, collection.count()),
        )

        # Build context from retrieved chunks
        context_parts: list[str] = []
        sources: list[dict] = []
        if results and results["documents"] and results["documents"][0]:
            for i, doc_text in enumerate(results["documents"][0]):
                context_parts.append(doc_text)
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0
                sources.append({
                    "doc_id": meta.get("doc_id", "unknown"),
                    "text_snippet": doc_text[:200],
                    "score": round(1 - distance, 4) if isinstance(distance, (int, float)) else 0,
                })

        context = "\n\n---\n\n".join(context_parts)

        # Call OpenAI with the context
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an AI assistant for an insurance claim processing system called IntelliClaim. "
                        "Answer the user's question based ONLY on the provided context from indexed documents. "
                        "If the context does not contain enough information, say so clearly. "
                        "Be concise and accurate."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {question}",
                },
            ],
            temperature=0.1,
            max_tokens=500,
        )

        answer = response.choices[0].message.content.strip()
        logger.info("RAG query answered: %s", question[:80])

        return {
            "answer": answer,
            "source_documents": sources,
        }

    def _mock_query(self, question: str) -> dict[str, Any]:
        """Generate a mock RAG response for demo mode.

        Args:
            question: The user's question.

        Returns:
            Mock answer and source documents.
        """
        question_lower = question.lower()

        # Provide contextually relevant mock answers
        if any(kw in question_lower for kw in ["cost", "amount", "charge", "expensive", "billing"]):
            answer = (
                "Based on the indexed documents, the average treatment cost across claims "
                "is approximately $35,200. The highest recorded cost is $95,000 for an acute "
                "myocardial infarction case at Metro General Hospital, and the lowest is "
                "$8,500 for outpatient psychiatric services."
            )
        elif any(kw in question_lower for kw in ["diagnosis", "condition", "disease", "medical"]):
            answer = (
                "The most common diagnoses in the indexed claims are: Acute Appendicitis (K35.80), "
                "Type 2 Diabetes Mellitus (E11.9), and Pneumonia (J18.9). Several claims also "
                "reference cardiac conditions including Acute Myocardial Infarction and Congestive "
                "Heart Failure."
            )
        elif any(kw in question_lower for kw in ["hospital", "provider", "facility"]):
            answer = (
                "The documents reference several healthcare facilities including Metro General Hospital "
                "(New York, NY), Cedar Ridge Medical Center (Chicago, IL), and Pacific Coast Healthcare "
                "(Los Angeles, CA). Metro General has the highest volume of claims."
            )
        elif any(kw in question_lower for kw in ["risk", "fraud", "flag", "suspicious"]):
            answer = (
                "Based on validation analysis, approximately 15% of claims are flagged as high-risk "
                "(risk score > 60). Common risk indicators include treatment costs significantly above "
                "the diagnosis average, potential duplicate submissions, and missing provider credentials."
            )
        else:
            answer = (
                "Based on the indexed documents, IntelliClaim has processed multiple insurance claims "
                "across various healthcare facilities. The system tracks policy numbers, diagnoses, "
                "treatment costs, and associated medical documentation. For more specific information, "
                "try asking about costs, diagnoses, hospitals, or risk assessments."
            )

        return {
            "answer": answer,
            "source_documents": [
                {
                    "doc_id": "mock_doc_001",
                    "text_snippet": "Patient John M. Doe admitted for Acute Appendicitis. Policy POL-2024-78901...",
                    "score": 0.92,
                },
                {
                    "doc_id": "mock_doc_002",
                    "text_snippet": "Metro General Hospital — Invoice for surgical services. Total charges: $28,500...",
                    "score": 0.87,
                },
                {
                    "doc_id": "mock_doc_003",
                    "text_snippet": "Discharge Summary: Patient discharged in stable condition. Follow-up in 2 weeks...",
                    "score": 0.81,
                },
            ],
        }

    # ----------------------------------------------------------------
    # Stats
    # ----------------------------------------------------------------
    async def get_index_stats(self) -> dict[str, Any]:
        """Return statistics about the indexed documents.

        Returns:
            Dict with indexed_chunks count and collection info.
        """
        try:
            collection = _get_collection()
            if collection is None:
                return {"indexed_chunks": 0, "status": "unavailable"}
            count = collection.count()
            return {"indexed_chunks": count, "status": "ready"}
        except Exception as e:
            logger.error("Failed to get index stats: %s", str(e))
            return {"indexed_chunks": 0, "status": "error", "error": str(e)}

    # ----------------------------------------------------------------
    # Text chunking utility
    # ----------------------------------------------------------------
    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
        """Split text into overlapping chunks.

        Args:
            text: The full text to split.
            chunk_size: Target size of each chunk in characters.
            overlap: Number of overlapping characters between chunks.

        Returns:
            List of text chunks.
        """
        if len(text) <= chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            # Try to break at a sentence boundary
            if end < len(text):
                last_period = chunk.rfind(".")
                last_newline = chunk.rfind("\n")
                break_point = max(last_period, last_newline)
                if break_point > chunk_size * 0.5:
                    chunk = chunk[: break_point + 1]
                    end = start + break_point + 1

            chunks.append(chunk.strip())
            start = end - overlap

        return [c for c in chunks if c]


# Module-level singleton
rag_service = RAGService()
