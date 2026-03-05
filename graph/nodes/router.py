#!/usr/bin/env python3
"""
Router Node - Tier 1 Optimized
Passes through route from extract_filters (no LLM, zero overhead).
Route is set by extract_filters: rag | structured | calculation | other.
"""

from graph.state import AgentState
from observability.logger import log_info


def route_query(state: AgentState) -> str:
    """
    Returns route from state (set by extract_filters). Defaults to "other" if missing.
    """
    route = (state.get("route") or "other").strip().lower()
    log_info(f"🚦 [Router] Route: {route}")
    return route if route in ("rag", "structured", "calculation", "other") else "other"
