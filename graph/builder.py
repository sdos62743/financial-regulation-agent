# graph/builder.py
"""
Main Graph Builder

This module constructs the complete LangGraph agent workflow.
It connects all nodes and defines the execution flow with conditional routing
and a controlled critic-based validation loop.
"""

from langgraph.graph import END, START, StateGraph

from graph.state import AgentState
from observability.logger import log_error, log_info, log_warning
from tools.registry import ToolRegistry

# Import production nodes
from .nodes.calculation import perform_calculation
from .nodes.classify_intent import classify_intent  # ← Fixed
from .nodes.direct_response import direct_response
from .nodes.extract_filters import extract_filters
from .nodes.merge import merge_outputs
from .nodes.rag import retrieve_docs
from .nodes.reasoning import generate_plan
from .nodes.router import route_query
from .nodes.structured import structured_extraction
from .nodes.validation import validate_response


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


def decide_end(state: AgentState) -> str:
    """Critic Decision - Controls validation loop with max iterations safety"""

    is_valid = state.get("validation_result", False)
    iterations = state.get("iterations", 0)

    # ==================== ORIGINAL CODE (Commented for debugging) ====================
    # if iterations >= 3:
    #     log_warning("Max validation iterations reached. Forcing completion.")
    #     return END
    #
    # if not is_valid:
    #     log_warning(f"Validation failed (Attempt {iterations+1}) - looping back to planner")
    #     return "planner_node"
    #
    # log_info("✅ Validation passed - ending graph")
    # return END
    # ================================================================================

    # ==================== TEMPORARY DEBUG VERSION ====================
    if iterations >= 1:
        log_warning(
            "Max validation iterations (debug mode) reached. Forcing completion."
        )
        return END

    if not is_valid:
        log_warning(
            f"Validation failed (Attempt {iterations+1}) - looping back to planner"
        )
        return "planner_node"

    log_info("✅ Validation passed - ending graph")
    return END
    # =================================================================


# ----------------------------------------------------------------------
# Graph Construction
# ----------------------------------------------------------------------
graph = StateGraph(AgentState)

# Nodes
graph.add_node("intent_node", classify_intent)
graph.add_node("extract_filters_node", extract_filters)  # ← New node added
graph.add_node("planner_node", generate_plan)
graph.add_node("retrieval_node", retrieve_docs)
graph.add_node("tools_node", call_tools)
graph.add_node("structured_node", structured_extraction)
graph.add_node("calculation_node", perform_calculation)
graph.add_node("synthesis_node", merge_outputs)
graph.add_node("critic_node", validate_response)
graph.add_node("direct_response_node", direct_response)

# ==================== ORIGINAL FLOW (Commented) ====================
# graph.add_edge(START, "intent_node")
# graph.add_edge("intent_node", "planner_node")
# =================================================================

# --- New Flow with Filter Extraction ---
graph.add_edge(START, "intent_node")
graph.add_edge("intent_node", "extract_filters_node")  # ← New edge
graph.add_edge("extract_filters_node", "planner_node")  # ← New edge

# --- Conditional routing after planning ---
graph.add_conditional_edges(
    "planner_node",
    route_query,
    {
        "rag": "retrieval_node",
        "structured": "structured_node",
        "calculation": "calculation_node",
        "other": "direct_response_node",
    },
)

# --- Flow after execution paths ---
graph.add_edge("retrieval_node", "tools_node")
graph.add_edge("tools_node", "synthesis_node")
graph.add_edge("structured_node", "synthesis_node")
graph.add_edge("calculation_node", "synthesis_node")
graph.add_edge("synthesis_node", "critic_node")

# --- Validation with loop control ---
graph.add_conditional_edges(
    "critic_node", decide_end, {"planner_node": "planner_node", END: END}
)

# Compile the final runnable graph
app = graph.compile()

log_info(
    "🚀 LangGraph regulatory agent workflow compiled and ready (with extract_filters)"
)
