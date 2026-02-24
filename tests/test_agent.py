# tests/test_agent.py
"""
End-to-End Agent Graph Tests

This file tests the complete LangGraph agent workflow from start to finish.
It covers different intents, routing, self-correction, and error scenarios.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from graph.builder import app
from graph.state import AgentState


@pytest.fixture
def sample_query():
    return "What did the FOMC say about interest rates in their June 2023 meeting?"


@pytest.mark.asyncio
async def test_full_agent_regulatory_lookup(sample_query):
    """Test complete agent flow for a typical regulatory lookup query"""
    result = await app.ainvoke({"query": sample_query})

    # Core assertions
    assert "synthesized_response" in result
    assert isinstance(result["synthesized_response"], str)
    assert len(result["synthesized_response"]) > 20

    # Should have gone through main path
    assert "retrieved_docs" in result
    assert "validation_result" in result


@pytest.mark.asyncio
async def test_full_agent_calculation_intent():
    """Test complete flow for a calculation-heavy query"""
    query = "Calculate the impact of a 25 basis point rate hike on bank capital ratios"

    result = await app.ainvoke({"query": query})

    assert "synthesized_response" in result
    assert "tool_outputs" in result
    # Should have triggered calculation path
    assert any(
        "calculation_result" in output for output in result.get("tool_outputs", [])
    )


@pytest.mark.asyncio
async def test_full_agent_structured_intent():
    """Test structured extraction intent"""
    query = "Extract the key dates and decisions from the latest FOMC minutes"

    result = await app.ainvoke({"query": query})

    assert "synthesized_response" in result
    assert "tool_outputs" in result
    # Should have structured data in tool outputs
    assert any("structured_data" in output for output in result.get("tool_outputs", []))


@pytest.mark.asyncio
async def test_self_correction_loop():
    """Test that the critic can trigger a loop back to planner"""
    # Force initial validation to fail
    initial_state = AgentState(
        query="Test query",
        intent="regulatory_lookup",
        plan=["Retrieve documents", "Synthesize answer"],
        retrieved_docs=[],
        tool_outputs=[],
        synthesized_response="This is a hallucinated answer with no sources.",
        validation_result=False,  # Force fail
        final_output="",
    )

    # Run a few steps manually to test loop
    from graph.builder import decide_end

    decision = decide_end(initial_state)

    assert decision == "planner"  # Should loop back


@pytest.mark.asyncio
async def test_agent_error_handling():
    """Test that the agent handles errors gracefully without crashing"""
    with patch(
        "graph.nodes.rag.retrieve_docs", side_effect=Exception("Retrieval failed")
    ):
        result = await app.ainvoke({"query": "This should trigger error handling"})

        # Should still return a response (with fallback)
        assert "synthesized_response" in result
        assert isinstance(result["synthesized_response"], str)


@pytest.mark.asyncio
async def test_agent_empty_query():
    """Test behavior with empty or invalid query"""
    result = await app.ainvoke({"query": "   "})

    assert "synthesized_response" in result
    # Should handle gracefully (probably fallback response)


# Performance / Smoke Test
@pytest.mark.asyncio
async def test_agent_response_time():
    """Basic performance smoke test"""
    import time

    start = time.perf_counter()

    result = await app.ainvoke({"query": "Summarize the latest FOMC statement"})

    duration = time.perf_counter() - start

    assert duration < 15.0  # Should respond within reasonable time
    assert "synthesized_response" in result
