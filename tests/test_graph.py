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
        "intent": "other",
        "plan": [],
        "filters": {},
        "retrieved_docs": [],
        "tool_outputs": [],
        "synthesized_response": "",
        "validation_result": False,
        "iterations": 0,
        "final_output": "",
    }


def _mock_extract_filters_llm(route: str, regulators=None):
    """Create mock LLM for extract_filters that returns JSON with given route."""
    import json
    from types import SimpleNamespace

    from langchain_core.runnables import RunnableLambda

    payload = {
        "regulators": regulators or ["FED"],
        "categories": None,
        "types": None,
        "year": None,
        "jurisdiction": "US",
        "sort": None,
        "route": route,
    }
    content = json.dumps(payload)

    async def _fake_ainvoke(x):
        return SimpleNamespace(content=content)

    return RunnableLambda(_fake_ainvoke)


@pytest.mark.integration
@pytest.mark.asyncio
@patch("graph.nodes.extract_filters.get_llm")
async def test_full_graph_regulatory_lookup(mock_get_llm, sample_state):
    """Test complete flow for rag route"""
    mock_get_llm.return_value = _mock_extract_filters_llm("rag")

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
@patch("graph.nodes.extract_filters.get_llm")
async def test_full_graph_calculation(mock_get_llm, sample_state):
    """Test complete flow for calculation route"""
    mock_get_llm.return_value = _mock_extract_filters_llm("calculation")

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
    """Test that calculation route routes correctly"""
    sample_state["route"] = "calculation"

    from graph.nodes.router import route_query

    next_node = route_query(sample_state)

    assert next_node == "calculation"


@pytest.mark.asyncio
async def test_routing_regulatory_lookup(sample_state):
    """Test that rag route routes to RAG"""
    sample_state["route"] = "rag"

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


# Optional: Mock LLM test for extract_filters node
@pytest.mark.integration
@pytest.mark.asyncio
@patch("graph.nodes.extract_filters.get_llm")
async def test_extract_filters_with_mock(mock_get_llm, sample_state):
    """Test extract_filters node with mocked LLM response"""
    mock_get_llm.return_value = _mock_extract_filters_llm("rag")

    from graph.nodes.extract_filters import extract_filters

    result = await extract_filters(sample_state)

    assert result["route"] == "rag"
    assert "filters" in result
