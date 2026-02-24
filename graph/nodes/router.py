#!/usr/bin/env python3
"""
Router Node - Tier 1 Optimized
Directs the graph flow with zero LLM overhead (pure Python logic).
Now aware of both intent and extracted filters.
"""

from graph.state import AgentState
from observability.logger import log_error, log_info


def route_query(state: AgentState) -> str:
    """
    Determines the next path based on intent + extracted filters.
    """
    intent = state.get("intent", "other").lower().strip()
    filters = state.get("filters", {}) or {}

    log_info(f"🚦 [Router] Evaluating path | Intent: {intent} | Filters: {filters}")

    # ==================== ORIGINAL LOGIC (Commented for reference) ====================
    # if "calculation" in intent:
    #     return "calculation"
    # if "structured" in intent:
    #     return "structured"
    # regulatory_keywords = ["regulatory_lookup", "reasoning", "lookup", "research", "rag"]
    # if any(k in intent for k in regulatory_keywords):
    #     return "rag"
    # return "other"
    # =================================================================================

    # 1. High-priority explicit intents (unchanged)
    if "calculation" in intent:
        log_info("➡️ Routed to: calculation")
        return "calculation"

    if "structured" in intent:
        log_info("➡️ Routed to: structured")
        return "structured"

    # 2. NEW: Smart filter-based boost
    has_strong_filters = bool(
        filters.get("regulators")
        or filters.get("year")
        or filters.get("doc_types")
        or filters.get("jurisdiction")
    )

    # 3. Regulatory / Research Path
    regulatory_keywords = [
        "regulatory_lookup",
        "reasoning",
        "lookup",
        "research",
        "rag",
    ]
    if any(k in intent for k in regulatory_keywords) or has_strong_filters:
        log_info("➡️ Routed to: rag (Parallel Retrieval + Tools)")
        return "rag"

    # 4. Fallback
    log_info("➡️ Routed to: other (Direct Response)")
    return "other"
