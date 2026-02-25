#!/usr/bin/env python3
"""
Router Node - Tier 1 Optimized
Directs the graph flow with zero LLM overhead (pure Python logic).
Now aware of both intent and extracted filters.
"""

from graph.state import AgentState
from observability.logger import log_info


def route_query(state: AgentState) -> str:
    """
    Determines the next path based on intent + extracted filters.
    """
    intent = (state.get("intent") or "other").lower().strip()
    filters = state.get("filters") or {}

    log_info(f"🚦 [Router] Evaluating path | Intent: {intent} | Filters: {filters}")

    # 1) High-priority explicit intents
    if "calculation" in intent:
        log_info("➡️ Routed to: calculation")
        return "calculation"

    if "structured" in intent:
        log_info("➡️ Routed to: structured")
        return "structured"

    # 2) Filter-based routing (Approach A schema)
    wants_latest = str(filters.get("sort", "")).lower() == "latest"

    has_strong_filters = bool(
        filters.get("regulators")
        or filters.get("year")
        or filters.get("types")
        or filters.get("categories")
        or filters.get("jurisdiction")
        or filters.get("sort")
    )
    # 3) Regulatory / research keywords OR filters imply RAG
    regulatory_keywords = {
        "regulatory_lookup",
        "reasoning",
        "lookup",
        "research",
        "rag",
    }
    if (
        any(k in intent for k in regulatory_keywords)
        or has_strong_filters
        or wants_latest
    ):
        log_info("➡️ Routed to: rag (Retrieval)")
        return "rag"

    # 4) Fallback
    log_info("➡️ Routed to: other (Direct Response)")
    return "other"
