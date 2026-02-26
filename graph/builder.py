# graph/builder.py
"""
Main Graph Builder

This module constructs the complete LangGraph agent workflow.
It connects all nodes and defines the execution flow with conditional routing
and a controlled critic-based validation loop.
"""

import os

from langgraph.graph import END, START, StateGraph

from graph.constants import (
    DEFAULT_MAX_VALIDATION_ITERATIONS,
    SAFE_CLARIFICATION_MSG,
    SAFE_MEETING_MSG,
)
from graph.state import AgentState
from observability.logger import log_error, log_info, log_warning
from tools.registry import ToolRegistry

# Import production nodes
from .nodes.calculation import perform_calculation
from .nodes.classify_intent import classify_intent
from .nodes.direct_response import direct_response
from .nodes.extract_filters import extract_filters
from .nodes.merge import merge_outputs
from .nodes.rag import retrieve_docs
from .nodes.reasoning import generate_plan
from .nodes.router import route_query
from .nodes.structured import structured_extraction
from .nodes.validation import validate_response


def finalize_response(state: AgentState) -> AgentState:
    """
    Ensures we always return a safe final_output at END.
    Prevents stale synthesized_response from leaking when validation fails.
    """
    is_valid = bool(state.get("validation_result", False))

    # Prefer existing final_output if present
    final_output = (state.get("final_output") or "").strip()
    if final_output:
        return {"final_output": final_output}

    # If invalid, force a safe user-facing message
    if not is_valid:
        query = (state.get("query") or "").strip()
        msg = SAFE_MEETING_MSG if "meeting" in query.lower() else SAFE_CLARIFICATION_MSG

        # Clear stale draft fields so controller cannot display them
        return {
            "final_output": msg,
            "synthesized_response": "",
            "response": "",
        }

    # Valid but no final_output: fallback to synthesized/response
    synthesized = (state.get("synthesized_response") or "").strip()
    response = (state.get("response") or "").strip()
    return {
        "final_output": synthesized
        or response
        or "I couldn’t generate an answer. Please rephrase."
    }


async def call_tools(state: AgentState) -> AgentState:
    """Tool Calling Node - Executes tools mentioned in the plan"""
    tool_outputs = []
    plan_steps = state.get("plan", [])

    for step in plan_steps:
        if "tool:" in step.lower():
            try:
                tool_part = step.split("tool:")[1].strip()
                tool_name = tool_part.split()[0]

                log_info(f"Executing tool: {tool_name}")
                output = await ToolRegistry.invoke(tool_name)
                tool_outputs.append(output)
            except Exception as e:
                log_error(f"Tool execution failed for step '{step}': {e}")

    return {"tool_outputs": tool_outputs}


def router_node(state: AgentState) -> dict:
    """Store route in state so post-retrieval branching knows where to go."""
    route = route_query(state)
    return {"route": route}


def route_after_planner(state: AgentState) -> str:
    """Send to retrieval for rag/structured/calculation; direct_response for other."""
    route = state.get("route", "other")
    if route in ("rag", "structured", "calculation"):
        return "retrieval_node"
    return "direct_response_node"


def route_after_retrieval(state: AgentState) -> str:
    """Branch to tools, structured, calculation, or synthesis based on route and plan."""
    route = state.get("route", "rag")
    if route == "structured":
        return "structured_node"
    if route == "calculation":
        return "calculation_node"
    # RAG path: only run tools when plan has tool: steps (Category 3.1)
    plan = state.get("plan") or []
    has_tool_steps = any("tool:" in str(s).lower() for s in plan)
    return "tools_node" if has_tool_steps else "synthesis_node"


def decide_end(state: AgentState) -> str:
    """Critic Decision - Controls validation loop with max iterations safety."""
    is_valid = state.get("validation_result", False)
    iterations = state.get("iterations", 0)
    max_iter = int(
        os.getenv("MAX_VALIDATION_ITERATIONS", str(DEFAULT_MAX_VALIDATION_ITERATIONS))
    )

    if iterations >= max_iter:
        log_warning(f"Max validation iterations ({max_iter}) reached. Forcing completion.")
        return END

    if not is_valid:
        log_warning(
            f"Validation failed (Attempt {iterations + 1}) - looping back to planner"
        )
        return "planner_node"

    log_info("✅ Validation passed - ending graph")
    return END


# ----------------------------------------------------------------------
# Graph Construction
# ----------------------------------------------------------------------
graph = StateGraph(AgentState)

# Nodes
graph.add_node("intent_node", classify_intent)
graph.add_node("extract_filters_node", extract_filters)
graph.add_node("planner_node", generate_plan)
graph.add_node("router_node", router_node)
graph.add_node("retrieval_node", retrieve_docs)
graph.add_node("tools_node", call_tools)
graph.add_node("structured_node", structured_extraction)
graph.add_node("calculation_node", perform_calculation)
graph.add_node("synthesis_node", merge_outputs)
graph.add_node("critic_node", validate_response)
graph.add_node("direct_response_node", direct_response)
graph.add_node("finalize_node", finalize_response)


# Flow with Filter Extraction
graph.add_edge(START, "intent_node")
graph.add_edge("intent_node", "extract_filters_node")  # ← New edge
graph.add_edge("extract_filters_node", "planner_node")  # ← New edge

# --- Planning -> Router -> Retrieval or Direct ---
graph.add_edge("planner_node", "router_node")
graph.add_conditional_edges(
    "router_node",
    route_after_planner,
    {
        "retrieval_node": "retrieval_node",
        "direct_response_node": "direct_response_node",
    },
)

# --- After retrieval: branch to tools, structured, calculation, or synthesis ---
# (Category 6: structured/calculation get docs via retrieval first)
# (Category 3.1: RAG skips tools when plan has no tool: steps)
graph.add_conditional_edges(
    "retrieval_node",
    route_after_retrieval,
    {
        "tools_node": "tools_node",
        "synthesis_node": "synthesis_node",
        "structured_node": "structured_node",
        "calculation_node": "calculation_node",
    },
)
graph.add_edge("tools_node", "synthesis_node")
graph.add_edge("structured_node", "synthesis_node")
graph.add_edge("calculation_node", "synthesis_node")
graph.add_edge("synthesis_node", "critic_node")

# --- Validation with loop control ---
graph.add_conditional_edges(
    "critic_node", decide_end, {"planner_node": "planner_node", END: "finalize_node"}
)
graph.add_edge("direct_response_node", "finalize_node")
graph.add_edge("finalize_node", END)

# Compile the final runnable graph
app = graph.compile()

log_info(
    "🚀 LangGraph regulatory agent workflow compiled and ready (with extract_filters)"
)
