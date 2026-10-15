"""Tests for the MCP server: tools run in-process through an MCP client against test_db.

Embeddings come from the conftest FakeEmbedder and provider calls from FakeGroq,
so no test reaches a real model.
"""

import pytest
from mcp import Client

import db.connection as db_conn
from mcp_server import mcp
from services.rag_service import rag_service

TOOLS = {"search_documents", "get_claim", "list_flagged_claims", "validate_claim"}


class _Session:
    """Opens an in-process MCP client per call.

    The client's anyio task group must be entered and exited in the same task,
    which an async yield fixture cannot guarantee.
    """

    async def list_tools(self):
        async with Client(mcp) as client:
            return (await client.list_tools()).tools

    async def call(self, name: str, **arguments):
        async with Client(mcp) as client:
            return await client.call_tool(name, arguments)


@pytest.fixture
def client(test_db):
    original_db = db_conn._database
    db_conn._database = test_db
    yield _Session()
    db_conn._database = original_db


async def _call(client, name: str, **arguments) -> dict:
    result = await client.call(name, **arguments)
    assert not result.is_error, result.content
    return result.structured_content


async def _error(client, name: str, **arguments) -> str:
    result = await client.call(name, **arguments)
    assert result.is_error
    return result.content[0].text


async def _index_test_documents(test_db) -> None:
    async for doc in test_db.documents.find():
        await rag_service.index_document(doc["_id"], doc["extracted_text"], {"filename": doc["filename"]})


# --- Tool listing ------------------------------------------------------------------


async def test_lists_the_four_tools_all_read_only(client):
    tools = await client.list_tools()

    assert {tool.name for tool in tools} == TOOLS
    assert all(tool.annotations.read_only_hint for tool in tools)
    assert all(tool.description for tool in tools)


async def test_tool_inputs_are_bounded(client):
    message = await _error(client, "search_documents", query="appendicitis", top_k=50)

    assert "top_k" in message


# --- get_claim ---------------------------------------------------------------------


async def test_get_claim_by_id_includes_its_documents_and_risk_level(client):
    claim = await _call(client, "get_claim", claim="claim-test-001")

    assert claim["id"] == "claim-test-001"
    assert claim["patient_name"] == "Jane Smith"
    assert claim["risk_level"] == "low"
    assert claim["created_at"].startswith("2024-01-16T11:00:00")
    assert [doc["filename"] for doc in claim["documents"]] == ["claim_form_test.pdf"]


async def test_get_claim_accepts_a_claim_number(client):
    claim = await _call(client, "get_claim", claim="CLM-002")

    assert claim["id"] == "claim-test-002"
    assert claim["risk_level"] == "high"
    assert claim["documents"] == []


async def test_get_claim_reports_an_unknown_claim(client):
    message = await _error(client, "get_claim", claim="CLM-404")

    assert "CLM-404" in message


# --- list_flagged_claims -----------------------------------------------------------


async def test_list_flagged_claims_returns_risky_claims_only(client):
    flagged = await _call(client, "list_flagged_claims")

    assert [claim["id"] for claim in flagged["claims"]] == ["claim-test-002"]
    assert flagged["total"] == 1
    assert flagged["claims"][0]["risk_flags"] == ["Treatment cost exceeds $50,000 threshold"]
    assert flagged["flag_threshold"] == 15


async def test_list_flagged_claims_orders_by_risk_score_and_respects_the_limit(client, test_db):
    await test_db.claims.update_one({"_id": "claim-test-001"}, {"$set": {"risk_score": 80.0}})

    flagged = await _call(client, "list_flagged_claims", limit=1)

    assert [claim["id"] for claim in flagged["claims"]] == ["claim-test-001"]
    assert flagged["total"] == 2


# --- validate_claim ----------------------------------------------------------------


async def test_validate_claim_without_a_provider_scores_on_rules_and_stores_nothing(client, test_db):
    result = await _call(client, "validate_claim", claim="CLM-002")

    assert result["claim_id"] == "claim-test-002"
    assert result["ai_review"]["status"] == "not_configured"
    assert {flag["origin"] for flag in result["flags"]} == {"rule"}
    assert any("50,000" in flag["description"] for flag in result["flags"])
    stored = await test_db.claims.find_one({"_id": "claim-test-002"})
    assert stored["risk_score"] == 65.0
    assert stored["updated_at"].year == 2024


async def test_validate_claim_reports_a_provider_failure(client, fake_groq, groq_errors):
    fake_groq.respond(groq_errors.connection())

    message = await _error(client, "validate_claim", claim="claim-test-001")

    assert "AI provider" in message


# --- search_documents --------------------------------------------------------------


async def test_search_documents_returns_matching_passages_without_a_model(client, test_db):
    await _index_test_documents(test_db)

    found = await _call(client, "search_documents", query="Type 2 Diabetes at Metro General", top_k=1)

    assert found["retrieval_mode"] == "hybrid"
    [result] = found["results"]
    assert result["doc_id"] == "doc-test-002"
    assert result["filename"] == "claim_form_test.pdf"
    assert "Metro General" in result["text"]


async def test_search_documents_on_an_empty_index_returns_no_results(client):
    found = await _call(client, "search_documents", query="appendicitis")

    assert found["results"] == []
