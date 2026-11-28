"""
IntelliClaim AI - Search index errors

Kept apart from services.rag_index so that main.py can register handlers
without importing LangChain, LlamaIndex and ChromaDB at startup.
"""


class VectorStoreUnavailableError(RuntimeError):
    """ChromaDB could not be opened."""


class IncompatibleIndexError(Exception):
    """The collection holds vectors from a different embedding model (HTTP 409).

    Stored vectors cannot be compared with the current model's, so searches
    and additions are refused until POST /api/rag/index-all rebuilds the index.
    """

    status_code = 409

    def __init__(self, stored: str, expected: str) -> None:
        self.detail = (
            f"The search index was built with a different embedding model ({stored}; this server uses "
            f"{expected}). Rebuild it with POST /api/rag/index-all."
        )
        super().__init__(self.detail)
