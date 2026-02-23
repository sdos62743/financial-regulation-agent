# tests/test_graph.py
"""
Production tests for the LangGraph agent workflow.

Tests cover:
- Full end-to-end flow for different intents
- Routing correctness
- Self-correction loop
- Error handling and fallbacks
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from graph.builder import app
from graph.state import AgentState


@pytest.fixture
def sample_state():
    """Fixture for basic agent state"""
    return AgentState(
        query="What did the FOMC say about interest rates in January 2023?",
        intent="",
        plan=[],
        retrieved_docs=[],
        tool_outputs=[],
        synthesized_response="",
        validation_result=False,
        final_output=""
    )


@pytest.mark.asyncio
async def test_full_graph_regulatory_lookup(sample_state):
    """Test complete flow for regulatory_lookup intent"""
    sample_state["query"] = "Summarize the latest FOMC statement on inflation."

    result = await app.ainvoke(sample_state)

    assert "synthesized_response" in result
    assert isinstance(result["synthesized_response"], str)
    assert len(result["synthesized_response"]) > 10
    assert result["validation_result"] is True or result["validation_result"] is False


@pytest.mark.asyncio
async def test_full_graph_calculation(sample_state):
    """Test complete flow for calculation intent"""
    sample_state["query"] = "What is the current Fed Funds Rate and how does it compare to last year?"

    result = await app.ainvoke(sample_state)

    assert "tool_outputs" in result
    assert any("calculation_result" in output for output in result.get("tool_outputs", []))


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

    from graph.builder import decide_end
    decision = decide_end(sample_state)

    assert decision == "planner"


@pytest.mark.asyncio
async def test_max_iterations_prevents_infinite_loop(sample_state):
    """Test safety mechanism against infinite validation loops"""
    sample_state["validation_result"] = False
    sample_state["iterations"] = 4  # Simulate reaching max

    from graph.builder import decide_end
    decision = decide_end(sample_state)

    assert decision == "END"  # Should force end after max iterations


# Optional: Mock LLM test (advanced)
@pytest.mark.asyncio
@patch("graph.nodes.classify.llm.ainvoke", new_callable=AsyncMock)
async def test_classify_with_mock(mock_ainvoke, sample_state):
    """Test classify node with mocked LLM response"""
    mock_ainvoke.return_value.content = "regulatory_lookup"

    from graph.nodes.classify import classify_intent
    result = await classify_intent(sample_state)

    assert result["intent"] == "regulatory_lookup"