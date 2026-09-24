"""
IntelliClaim AI — AI Evaluation Tests

Tests that demonstrate AI behavior quality:
1. RAG retrieval relevance — mock queries return contextually relevant answers
"""

import pytest
import asyncio

from services.rag_service import RAGService


@pytest.mark.asyncio
async def test_rag_retrieval_relevance():
    """RAG query returns a contextually relevant answer from mock data.

    Even in demo mode, the mock query should provide semantically
    appropriate answers based on keyword matching.
    """
    rag = RAGService()

    test_cases = [
        ("What is the average treatment cost?", "cost"),
        ("Tell me about diagnoses", "diagnoses"),
        ("Which hospitals are mentioned?", "hospital"),
        ("Are there any fraud risks?", "risk"),
    ]

    for question, expected_keyword in test_cases:
        result = await rag.query(question, top_k=3)
        assert "answer" in result
        assert "source_documents" in result
        assert len(result["source_documents"]) > 0
        # The mock answer should contain a relevant keyword
        answer_lower = result["answer"].lower()
        assert expected_keyword in answer_lower, (
            f"Expected '{expected_keyword}' in answer for '{question}', got: {answer_lower[:100]}"
        )
