# MCP server

`backend/mcp_server.py` exposes IntelliClaim to any [Model Context Protocol](https://modelcontextprotocol.io) client, so an agent can look up claims and source documents with the same services the web app uses.

## Tools

All four tools are read-only (`readOnlyHint: true`).

| Tool | Arguments | Returns | Needs an AI provider |
| --- | --- | --- | --- |
| `search_documents` | `query`, `top_k` (1–20, default 5) | Matching passages: document id, filename, page, score and text, plus the retrieval mode | No (retrieval only) |
| `get_claim` | `claim` (id or claim number) | The claim's fields, status, risk score, risk level and flags, and its linked documents | No |
| `list_flagged_claims` | `limit` (1–50, default 10) | Claims flagged or at medium/high risk, highest score first, with the flag threshold | No |
| `validate_claim` | `claim` (id or claim number) | Risk score, level and every flag with its severity and origin (`rule` or `ai`) | Optional: without one the AI review is skipped and `ai_review.status` is `not_configured` |

`validate_claim` never writes. To store a validation result, use `POST /api/validate/{claim_id}`.

Errors (an unknown claim, an index built with another embedding model, a failing AI provider) come back as tool errors with a readable message.

## Running it

The server reads the same settings as the API (`backend/.env`: `MONGODB_URI`, `MONGODB_DB_NAME`, `CHROMA_PERSIST_DIR` and the provider keys). Point `CHROMA_PERSIST_DIR` at the API's index directory to search the documents the API has indexed.

```bash
cd backend
pip install -r requirements.txt
python mcp_server.py                                   # stdio
python mcp_server.py --transport streamable-http --port 8001   # http://127.0.0.1:8001/mcp
```

A client that launches stdio servers takes a configuration like this (adjust the paths):

```json
{
  "mcpServers": {
    "intelliclaim": {
      "command": "/path/to/intelliclaim-ai/backend/.venv/bin/python",
      "args": ["/path/to/intelliclaim-ai/backend/mcp_server.py"]
    }
  }
}
```

Logs go to stderr, so stdout carries only protocol messages.

## Tests

`backend/tests/test_mcp_server.py` drives every tool through an in-process MCP client against the test database, with fake embeddings and a fake AI provider:

```bash
cd backend
pytest tests/test_mcp_server.py
```
