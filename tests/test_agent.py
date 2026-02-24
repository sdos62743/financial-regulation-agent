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


@pytest.mark.integration
@pytest.mark.asyncio
@patch("graph.nodes.classify_intent.get_llm")
async def test_full_agent_regulatory_lookup(mock_get_llm, sample_query):
    """Test complete agent flow for a typical regulatory lookup query"""
    # Mock LLM to return regulatory_lookup intent so we exercise RAG path
    mock_llm = AsyncMock()
    mock_structured = AsyncMock()
    mock_parsed = type("Parsed", (), {"category": "regulatory_lookup"})()
    mock_structured.ainvoke.return_value = {"parsed": mock_parsed, "raw": AsyncMock()}
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_llm.return_value = mock_llm

    result = await app.ainvoke({"query": sample_query})

    # Response can be synthesized_response (RAG path) or final_output (direct path)
    response = result.get("synthesized_response") or result.get("final_output", "")
    assert isinstance(response, str)
    assert len(response) > 20

    # Should have gone through main path
    assert "retrieved_docs" in result or "validation_result" in result


@pytest.mark.integration
@pytest.mark.asyncio
@patch("graph.nodes.classify_intent.get_llm")
async def test_full_agent_calculation_intent(mock_get_llm):
    """Test complete flow for a calculation-heavy query"""
    mock_llm = AsyncMock()
    mock_structured = AsyncMock()
    mock_parsed = type("Parsed", (), {"category": "calculation"})()
    mock_structured.ainvoke.return_value = {"parsed": mock_parsed, "raw": AsyncMock()}
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_llm.return_value = mock_llm

    query = "Calculate the impact of a 25 basis point rate hike on bank capital ratios"
    result = await app.ainvoke({"query": query})

    response = result.get("synthesized_response") or result.get("final_output", "")
    assert isinstance(response, str)
    # Calculation path: tool_outputs or calculation_node output
    tool_outputs = result.get("tool_outputs", [])
    has_calc = any(
        "calculation" in str(o).lower() or "calculation_result" in str(o)
        for o in tool_outputs
    )
    assert "tool_outputs" in result or has_calc or len(response) > 0


@pytest.mark.integration
@pytest.mark.asyncio
@patch("graph.nodes.classify_intent.get_llm")
async def test_full_agent_structured_intent(mock_get_llm):
    """Test structured extraction intent"""
    mock_llm = AsyncMock()
    mock_structured = AsyncMock()
    mock_parsed = type("Parsed", (), {"category": "structured"})()
    mock_structured.ainvoke.return_value = {"parsed": mock_parsed, "raw": AsyncMock()}
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_llm.return_value = mock_llm

    query = "Extract the key dates and decisions from the latest FOMC minutes"
    result = await app.ainvoke({"query": query})

    response = result.get("synthesized_response") or result.get("final_output", "")
    assert isinstance(response, str)
    tool_outputs = result.get("tool_outputs", [])
    has_structured = any(
        "structured" in str(o).lower() or "structured_data" in str(o)
        for o in tool_outputs
    )
    assert has_structured or len(response) > 0


@pytest.mark.asyncio
async def test_self_correction_loop():
    """Test that the critic can trigger a loop back to planner"""
    # Force initial validation to fail
    initial_state = {
        "query": "Test query",
        "intent": "regulatory_lookup",
        "plan": ["Retrieve documents", "Synthesize answer"],
        "filters": {},
        "retrieved_docs": [],
        "tool_outputs": [],
        "synthesized_response": "This is a hallucinated answer with no sources.",
        "validation_result": False,
        "iterations": 0,
        "final_output": "",
    }

    # Run a few steps manually to test loop
    from graph.builder import decide_end

    decision = decide_end(initial_state)

    assert decision == "planner_node"  # Should loop back


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_error_handling():
    """Test that the agent handles errors gracefully without crashing"""
    with patch(
        "graph.nodes.rag.hybrid_search",
        new_callable=AsyncMock,
        side_effect=Exception("Retrieval failed"),
    ):
        result = await app.ainvoke({"query": "This should trigger error handling"})

        # Should still return a response (synthesized or final fallback)
        response = result.get("synthesized_response") or result.get("final_output", "")
        assert isinstance(response, str)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_empty_query():
    """Test behavior with empty or invalid query"""
    result = await app.ainvoke({"query": "   "})

    response = result.get("synthesized_response") or result.get("final_output", "")
    assert isinstance(response, str)


# Performance / Smoke Test
@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_response_time():
    """Basic performance smoke test"""
    import time

    start = time.perf_counter()

    result = await app.ainvoke({"query": "Summarize the latest FOMC statement"})

    duration = time.perf_counter() - start

    assert duration < 15.0  # Should respond within reasonable time
    response = result.get("synthesized_response") or result.get("final_output", "")
    assert isinstance(response, str)
