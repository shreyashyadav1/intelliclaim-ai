"""
IntelliClaim AI - MCP server

Exposes the claim database and the document search index to MCP clients
(an IDE, a desktop assistant or an agent framework) as four read-only tools:

- search_documents: hybrid (or vector) retrieval over the indexed documents.
  Retrieval only, so it needs no AI provider.
- get_claim: one claim, by id or claim number, with its linked documents.
- list_flagged_claims: claims at medium or high risk, highest score first.
- validate_claim: runs the rule-based and AI-assisted validation and returns
  the result without storing it (the API's POST /api/validate/{id} stores it).

The tools call the same services as the FastAPI routers, so answers match
the web app. Run it over stdio (the default) or Streamable HTTP:

    python mcp_server.py
    python mcp_server.py --transport streamable-http --port 8001

Configuration comes from the same settings as the API (MONGODB_URI,
CHROMA_PERSIST_DIR, provider keys). Logs go to stderr, which keeps stdout
free for the stdio transport.
"""

import argparse
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

import db.connection as db_connection
from config import settings
from services.llm import LLMError
from services.rag_errors import IncompatibleIndexError, VectorStoreUnavailableError
from services.rag_service import rag_service
from services.risk_levels import flagged_claims_query, risk_level
from services.validation_service import validation_service

logger = logging.getLogger("intelliclaim.mcp")

INSTRUCTIONS = (
    "IntelliClaim holds insurance claims extracted from uploaded documents. Use search_documents to find "
    "passages in the source documents, get_claim to read a claim and its documents, list_flagged_claims to "
    "find risky claims, and validate_claim to see why a claim scores the way it does. Every tool is read-only."
)

_SUMMARY_FIELDS = ("claim_number", "patient_name", "policy_number", "treatment_cost", "status", "risk_score")


@asynccontextmanager
async def _database_lifespan(_server: MCPServer) -> AsyncIterator[None]:
    """Connect to MongoDB for the server's lifetime, unless a connection already exists."""
    owns_connection = db_connection._database is None
    if owns_connection:
        await db_connection.connect_db()
    try:
        yield
    finally:
        if owns_connection:
            await db_connection.close_db()


mcp = MCPServer(name="intelliclaim", instructions=INSTRUCTIONS, lifespan=_database_lifespan)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _plain(value: Any) -> Any:
    """MongoDB values as JSON-friendly ones (datetimes become ISO 8601 strings)."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _with_id(record: dict[str, Any]) -> dict[str, Any]:
    record = dict(record)
    record["id"] = record.pop("_id")
    return _plain(record)


async def _find_claim(claim: str) -> dict[str, Any]:
    """A claim by its id, or else by its claim number."""
    db = db_connection.get_database()
    record = await db.claims.find_one({"_id": claim}) or await db.claims.find_one({"claim_number": claim})
    if record is None:
        raise ToolError(f"No claim has the id or claim number {claim!r}.")
    return record


@mcp.tool(annotations=READ_ONLY)
async def search_documents(
    query: Annotated[str, Field(min_length=1, max_length=1000, description="What to look for, in plain language")],
    top_k: Annotated[int, Field(ge=1, le=20, description="Number of passages to return")] = 5,
) -> dict[str, Any]:
    """Find the passages in the indexed claim documents that best match a query.

    Each result has the document id and filename, the page (when known), a
    relevance score and the passage text. No AI model is involved.
    """
    try:
        return await rag_service.search(query.strip(), top_k=top_k)
    except (IncompatibleIndexError, VectorStoreUnavailableError) as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(annotations=READ_ONLY)
async def get_claim(
    claim: Annotated[str, Field(min_length=1, max_length=100, description="Claim id or claim number")],
) -> dict[str, Any]:
    """Read one claim: its extracted fields, status, risk score and flags, and its source documents."""
    record = await _find_claim(claim.strip())
    db = db_connection.get_database()
    documents = await db.documents.find(
        {"_id": {"$in": record.get("document_ids", [])}},
        {"filename": 1, "document_class": 1, "processing_status": 1, "page_count": 1},
    ).to_list(length=100)
    return {
        **_with_id(record),
        "risk_level": risk_level(record.get("risk_score") or 0.0),
        "documents": [_with_id(doc) for doc in documents],
    }


@mcp.tool(annotations=READ_ONLY)
async def list_flagged_claims(
    limit: Annotated[int, Field(ge=1, le=50, description="Maximum number of claims to return")] = 10,
) -> dict[str, Any]:
    """List claims flagged for review (status "flagged" or at least medium risk), highest risk score first."""
    db = db_connection.get_database()
    query = flagged_claims_query()
    records = await db.claims.find(query).sort("risk_score", -1).limit(limit).to_list(length=limit)
    claims = [
        {
            "id": record["_id"],
            **{name: record.get(name) for name in _SUMMARY_FIELDS},
            "risk_level": risk_level(record.get("risk_score") or 0.0),
            "risk_flags": record.get("risk_flags", []),
        }
        for record in records
    ]
    return {
        "claims": claims,
        "total": await db.claims.count_documents(query),
        "flag_threshold": settings.RISK_FLAG_THRESHOLD,
    }


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
async def validate_claim(
    claim: Annotated[str, Field(min_length=1, max_length=100, description="Claim id or claim number")],
) -> dict[str, Any]:
    """Run validation on a claim and explain its risk, without changing the stored claim.

    Returns the composite risk score and level and every flag with its
    severity and origin ("rule" or "ai"). The AI review runs only when an AI
    provider is configured; ai_review.status says whether it did.
    """
    record = await _find_claim(claim.strip())
    try:
        result = await validation_service.validate_claim(record)
    except LLMError as exc:
        raise ToolError(exc.detail) from exc
    return {"claim_id": record["_id"], "claim_number": record.get("claim_number"), **result}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the IntelliClaim MCP server.")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1", help="Streamable HTTP only")
    parser.add_argument("--port", type=int, default=8001, help="Streamable HTTP only")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        mcp.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
