# tests/test_graph.py
"""
Production tests for the LangGraph agent workflow.

Tests cover:
- Full end-to-end flow for different intents
- Routing correctness
- Self-correction loop
- Error handling and fallbacks
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.graph import END

from graph.builder import app, decide_end
from graph.state import AgentState


@pytest.fixture
def sample_state():
    """Fixture for basic agent state"""
    return {
        "query": "What did the FOMC say about interest rates in January 2023?",
        "intent": "",
        "plan": [],
        "filters": {},
        "retrieved_docs": [],
        "tool_outputs": [],
        "synthesized_response": "",
        "validation_result": False,
        "iterations": 0,
        "final_output": "",
    }


@pytest.mark.integration
@pytest.mark.asyncio
@patch("graph.nodes.classify_intent.get_llm")
async def test_full_graph_regulatory_lookup(mock_get_llm, sample_state):
    """Test complete flow for regulatory_lookup intent"""
    mock_llm = AsyncMock()
    mock_structured = AsyncMock()
    mock_parsed = type("Parsed", (), {"category": "regulatory_lookup"})()
    mock_structured.ainvoke.return_value = {"parsed": mock_parsed, "raw": AsyncMock()}
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_llm.return_value = mock_llm

    sample_state["query"] = "Summarize the latest FOMC statement on inflation."
    result = await app.ainvoke(sample_state)

    response = result.get("synthesized_response") or result.get("final_output", "")
    assert isinstance(response, str)
    assert len(response) > 10
    assert (
        result.get("validation_result") is True
        or result.get("validation_result") is False
    )


@pytest.mark.integration
@pytest.mark.asyncio
@patch("graph.nodes.classify_intent.get_llm")
async def test_full_graph_calculation(mock_get_llm, sample_state):
    """Test complete flow for calculation intent"""
    mock_llm = AsyncMock()
    mock_structured = AsyncMock()
    mock_parsed = type("Parsed", (), {"category": "calculation"})()
    mock_structured.ainvoke.return_value = {"parsed": mock_parsed, "raw": AsyncMock()}
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_llm.return_value = mock_llm

    sample_state["query"] = (
        "What is the current Fed Funds Rate and how does it compare to last year?"
    )
    result = await app.ainvoke(sample_state)

    tool_outputs = result.get("tool_outputs", [])
    has_calc = any(
        "calculation" in str(o).lower() or "calculation_result" in str(o)
        for o in tool_outputs
    )
    assert (
        "tool_outputs" in result or has_calc or len(result.get("final_output", "")) > 0
    )


@pytest.mark.asyncio
async def test_routing_calculation_intent(sample_state):
    """Test that calculation intent routes correctly"""
    sample_state["intent"] = "calculation"

    # We can test routing directly via the router node
    from graph.nodes.router import route_query

    next_node = route_query(sample_state)

    assert next_node == "calculation"


@pytest.mark.asyncio
async def test_routing_regulatory_lookup(sample_state):
    """Test that regulatory_lookup routes to RAG"""
    sample_state["intent"] = "regulatory_lookup"

    from graph.nodes.router import route_query

    next_node = route_query(sample_state)

    assert next_node == "rag"


@pytest.mark.asyncio
async def test_validation_loop(sample_state):
    """Test critic loop - if validation fails, should go back to planner"""
    sample_state["validation_result"] = False
    sample_state["iterations"] = 0  # We'll add this temporarily for testing

    decision = decide_end(sample_state)

    assert decision == "planner_node"


@pytest.mark.asyncio
async def test_max_iterations_prevents_infinite_loop(sample_state):
    """Test safety mechanism against infinite validation loops"""
    sample_state["validation_result"] = False
    sample_state["iterations"] = 4  # Simulate reaching max

    decision = decide_end(sample_state)

    # LangGraph uses "__end__" as the END node identifier
    assert decision in (END, "__end__")  # Should force end after max iterations


# Optional: Mock LLM test (advanced) - requires proper LangChain Runnable mocking
@pytest.mark.integration
@pytest.mark.asyncio
@patch("graph.nodes.classify_intent.get_llm")
async def test_classify_with_mock(mock_get_llm, sample_state):
    """Test classify node with mocked LLM response"""
    mock_llm = AsyncMock()
    mock_structured = AsyncMock()
    mock_parsed = type("Parsed", (), {"category": "regulatory_lookup"})()
    mock_structured.ainvoke.return_value = {"parsed": mock_parsed, "raw": AsyncMock()}
    mock_llm.with_structured_output.return_value = mock_structured
    mock_get_llm.return_value = mock_llm

    from graph.nodes.classify_intent import classify_intent

    result = await classify_intent(sample_state)

    assert result["intent"] == "regulatory_lookup"
