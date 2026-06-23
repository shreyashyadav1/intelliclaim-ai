"""
IntelliClaim AI - RAG (Retrieval-Augmented Generation) Service

Indexes documents into ChromaDB via LlamaIndex (VectorStoreIndex + ChromaVectorStore)
and answers natural-language questions using a LangChain LCEL retrieval chain
(OpenAI Embeddings + ChatOpenAI + Chroma retriever). Falls back to mock responses
when OpenAI keys are not configured.
"""

import logging
import os
from typing import Any

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-initialised singletons for vector store and LangChain components
# ---------------------------------------------------------------------------
_chroma_client = None
_chroma_collection = None


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
            _chroma_collection = client.get_or_create_collection(
                name="intelliclaim_docs",
                metadata={"hnsw:space": "cosine"},
            )
    return _chroma_collection


def _get_langchain_vectorstore():
    """Return a LangChain Chroma vector store with OpenAI embeddings."""
    from langchain_community.vectorstores import Chroma
    from langchain_openai import OpenAIEmbeddings

    client = _get_chroma_client()
    if client is None:
        return None

    return Chroma(
        client=client,
        collection_name="intelliclaim_docs",
        embedding_function=OpenAIEmbeddings(model="text-embedding-3-small"),
    )


class RAGService:
    """Retrieval-Augmented Generation service for document Q&A."""

    # ----------------------------------------------------------------
    # Document indexing — LlamaIndex + OpenAI Embeddings + ChromaDB
    # ----------------------------------------------------------------
    async def index_document(self, doc_id: str, text: str, metadata: dict) -> bool:
        """Index a document's text using LlamaIndex + ChromaVectorStore.

        Creates a LlamaIndex Document, splits it into nodes, generates
        OpenAI embeddings, and persists vectors into ChromaDB.

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

        if not settings.has_openai_key and not settings.has_groq_key:
            return self._index_demo(doc_id, text, metadata)

        if settings.has_groq_key and not settings.has_openai_key:
            return await self._index_with_groq(doc_id, text, metadata)

        try:
            from llama_index.core import Document, VectorStoreIndex, StorageContext
            from llama_index.vector_stores.chroma import ChromaVectorStore
            from llama_index.embeddings.openai import OpenAIEmbedding
            import chromadb

            # Build the LlamaIndex Chroma vector store wrapper
            chroma_client = _get_chroma_client()
            if chroma_client is None:
                return False

            chroma_collection = chroma_client.get_or_create_collection(
                name="intelliclaim_docs",
                metadata={"hnsw:space": "cosine"},
            )
            vector_store = ChromaVectorStore(chroma_collection=chroma_collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            # Create LlamaIndex Document with enriched metadata
            doc = Document(text=text, metadata={**metadata, "doc_id": doc_id})

            # Build the index — this triggers OpenAI embedding generation
            index = VectorStoreIndex.from_documents(
                [doc],
                storage_context=storage_context,
                embed_model=OpenAIEmbedding(model="text-embedding-3-small"),
                show_progress=False,
            )

            logger.info("LlamaIndex indexed document %s into %d nodes", doc_id, len(index.docstore.docs))
            return True

        except Exception as e:
            logger.error("LlamaIndex indexing failed for %s: %s", doc_id, str(e))
            return False

    async def _index_with_groq(self, doc_id: str, text: str, metadata: dict) -> bool:
        """Index document using fastembed embeddings + ChromaDB."""
        try:
            from fastembed import TextEmbedding

            collection = _get_chroma_collection()
            if collection is None:
                return False

            chunks = self._chunk_text(text, chunk_size=500, overlap=50)
            ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{**metadata, "doc_id": doc_id, "chunk_index": i} for i in range(len(chunks))]

            embed_model = TextEmbedding()
            chunk_embeddings = [emb.tolist() for emb in embed_model.embed(chunks)]

            collection.upsert(ids=ids, documents=chunks, embeddings=chunk_embeddings, metadatas=metadatas)
            logger.info("Groq-indexed %d chunks for document %s", len(chunks), doc_id)
            return True
        except Exception as e:
            logger.error("Groq indexing failed for %s: %s", doc_id, str(e))
            return False

    def _index_demo(self, doc_id: str, text: str, metadata: dict) -> bool:
        """Demo-mode fallback: raw Chroma upsert without embeddings."""
        try:
            collection = _get_chroma_collection()
            if collection is None:
                return False

            chunks = self._chunk_text(text, chunk_size=500, overlap=50)
            ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
            metadatas = [{**metadata, "doc_id": doc_id, "chunk_index": i} for i in range(len(chunks))]

            collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
            logger.info("Demo-indexed %d chunks for document %s", len(chunks), doc_id)
            return True
        except Exception as e:
            logger.error("Demo indexing failed for %s: %s", doc_id, str(e))
            return False

    # ----------------------------------------------------------------
    # Query — LangChain LCEL retrieval chain + OpenAI Embeddings
    # ----------------------------------------------------------------
    async def query(self, question: str, top_k: int = 5) -> dict[str, Any]:
        """Answer a natural-language question using LangChain + ChromaDB.

        Uses a LangChain LCEL chain:
            retriever (Chroma + OpenAI Embeddings) → context formatting
            → ChatPromptTemplate → ChatOpenAI (GPT-4o) → StrOutputParser

        Falls back to mock responses when OpenAI keys are not configured.

        Args:
            question: The user's natural-language question.
            top_k: Number of source chunks to retrieve.

        Returns:
            Dict with 'answer' (str) and 'source_documents' (list).
        """
        if settings.has_openai_key:
            try:
                return await self._query_with_langchain(question, top_k)
            except Exception as e:
                logger.warning("LangChain/OpenAI query failed, trying Groq: %s", str(e))

        if settings.has_groq_key:
            try:
                return await self._query_with_groq(question, top_k)
            except Exception as e:
                logger.warning("Groq query failed, returning mock: %s", str(e))

        return self._mock_query(question)

    async def _query_with_langchain(self, question: str, top_k: int = 5) -> dict[str, Any]:
        """Execute a RAG query using a LangChain LCEL chain.

        Components used:
        - OpenAIEmbeddings (text-embedding-3-small) for vector retrieval
        - Chroma vector store (via LangChain wrapper) for document retrieval
        - ChatPromptTemplate for system prompt
        - ChatOpenAI (GPT-4o) for generation
        - StrOutputParser for clean output
        """
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.runnables import RunnablePassthrough, RunnableLambda
        from langchain_core.output_parsers import StrOutputParser
        from langchain_openai import ChatOpenAI

        vectorstore = _get_langchain_vectorstore()
        if vectorstore is None or vectorstore._collection.count() == 0:
            return {
                "answer": "No documents have been indexed yet. Please upload and index some documents first.",
                "source_documents": [],
            }

        # LangChain retriever backed by Chroma + OpenAI Embeddings
        retriever = vectorstore.as_retriever(search_kwargs={"k": top_k})

        # Retrieve once — reused for both the chain context and sources metadata
        docs = retriever.invoke(question)
        if not docs:
            return {
                "answer": "No relevant documents were found for your question.",
                "source_documents": [],
            }

        context = "\n\n---\n\n".join(d.page_content for d in docs)

        sources = [
            {
                "doc_id": doc.metadata.get("doc_id", "unknown"),
                "text_snippet": doc.page_content[:200],
                "score": getattr(doc, "score", 0.0),
            }
            for doc in docs
        ]

        # LangChain LCEL chain — context is pre-built to avoid double retrieval
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are an AI assistant for an insurance claim processing system called IntelliClaim. "
                "Answer the user's question based ONLY on the provided context from indexed documents. "
                "If the context does not contain enough information, say so clearly. "
                "Be concise and accurate.",
            ),
            (
                "human",
                "Context:\n{context}\n\nQuestion: {question}",
            ),
        ])

        llm = ChatOpenAI(model="gpt-4o", temperature=0.1, max_tokens=500)

        chain = (
            {"context": RunnableLambda(lambda _: context), "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

        answer = chain.invoke(question)
        logger.info("LangChain RAG answered: %s", question[:80])

        return {
            "answer": answer,
            "source_documents": sources,
        }

    async def _query_with_groq(self, question: str, top_k: int = 5) -> dict[str, Any]:
        """RAG query using fastembed embeddings → Chroma retrieval → Groq generation."""
        from fastembed import TextEmbedding
        from groq import Groq

        collection = _get_chroma_collection()
        if collection is None or collection.count() == 0:
            return {
                "answer": "No documents have been indexed yet. Please upload and index some documents first.",
                "source_documents": [],
            }

        embed_model = TextEmbedding()
        query_embedding = next(embed_model.embed([question])).tolist()

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        documents = results["documents"][0] if results["documents"] else []
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        if not documents:
            return {"answer": "No relevant documents found.", "source_documents": []}

        context = "\n\n---\n\n".join(documents)
        sources = [
            {
                "doc_id": meta.get("doc_id", "unknown"),
                "text_snippet": doc[:200],
                "score": round(1 - dist, 3),
            }
            for doc, meta, dist in zip(documents, metadatas, distances)
        ]

        prompt = (
            "You are an AI assistant for IntelliClaim, an insurance claim processing system. "
            "Answer based ONLY on the provided context. Be concise and accurate.\n\n"
            f"Context:\n{context}\n\nQuestion: {question}"
        )

        client = Groq(api_key=settings.GROQ_API_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
        )

        logger.info("Groq RAG answered: %s", question[:80])
        return {"answer": response.choices[0].message.content, "source_documents": sources}

    def _mock_query(self, question: str) -> dict[str, Any]:
        """Generate a mock RAG response for demo mode."""
        question_lower = question.lower()

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
        """Return statistics about the indexed documents."""
        try:
            collection = _get_chroma_collection()
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
        """Split text into overlapping chunks."""
        if len(text) <= chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
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
