#!/usr/bin/env python3
"""
Extract Filters Node - Tier 1 Optimized
Uses LLM to intelligently extract metadata filters from user query.
"""

import asyncio
import json
from typing import Any, Dict

from observability.logger import log_error, log_info
from observability.metrics import record_token_usage
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from app.llm_config import get_llm


async def extract_filters(state: AgentState) -> Dict[str, Any]:
    """
    Extract structured metadata filters from the user query using LLM.
    """
    query = state.get("query", "").strip()

    log_info(f"🔍 [Extract Filters Node] Analyzing query for filters: {query[:80]}...")

    # Build minimal context (we usually only need the query)
    context = f"User Query: {query}"

    try:
        llm = get_llm()
        filter_prompt = load_prompt("extract_filters")   # You need to create this prompt file
        chain = filter_prompt | llm

        # Execute
        raw_response = await chain.ainvoke({"query": query})

        result_text = raw_response.content.strip()

        # Parse JSON safely
        try:
            filters = json.loads(result_text)
        except json.JSONDecodeError:
            log_error(f"Failed to parse JSON from filter extraction: {result_text[:200]}")
            filters = {}  # Safe fallback

        # Clean up and normalize
        cleaned_filters = {
            "regulators": filters.get("regulators") or None,
            "year": filters.get("year") or None,
            "doc_types": filters.get("doc_types") or None,
            "jurisdiction": filters.get("jurisdiction") or None,
        }

        log_info(f"✅ [Extract Filters Node] Extracted: {cleaned_filters}")

        # Background metrics logging (non-blocking, like your calculation node)
        asyncio.create_task(_log_filter_metrics(llm, raw_response))

        # Return in a clean format for downstream nodes
        return {
            "filters": cleaned_filters
        }

    except Exception as e:
        log_error(f"❌ [Extract Filters Node] Failed: {e}")
        return {
            "filters": {}   # Safe fallback - no filtering
        }


async def _log_filter_metrics(llm, response):
    """Internal helper to log token usage without blocking the main node."""
    try:
        model_name = getattr(llm, "model", "gemini-1.5-flash")
        metadata = getattr(response, "response_metadata", {}) or {}
        usage = metadata.get("usage_metadata") or metadata.get("token_usage") or {}
        token_count = usage.get("total_tokens", 0)

        record_token_usage(model_name, "extract_filters_node", token_count)
        log_info(f"✅ [Extract Filters Node] Finished | Tokens: {token_count}")
    except Exception:
        pass   # Never let metrics break the flow