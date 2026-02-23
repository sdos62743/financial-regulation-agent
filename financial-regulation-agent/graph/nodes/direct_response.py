#!/usr/bin/env python3
"""
Direct Response Node - Tier 1 Optimized
Handles greetings and general queries with zero artificial latency.
"""

import asyncio
from typing import Dict, Any
from graph.state import AgentState
from app.llm_config import get_llm
from graph.prompts.loader import load_prompt
from observability.logger import log_info, log_error
from observability.metrics import record_token_usage

async def direct_response(state: AgentState) -> Dict[str, Any]:
    query = state.get("query", "")
    intent = state.get("intent", "other")
    
    log_info(f"🚀 [Direct Response] Processing '{intent}' intent")

    try:
        llm = get_llm()
        
        # PERF: Use the cached prompt loader instead of hardcoded strings.
        # This allows you to update the 'small talk' personality in the YAML file.
        prompt_template = load_prompt("direct_response")
        
        # Execute the conversation
        # We use a simple invoke for speed since no structured output is required.
        chain = prompt_template | llm
        response = await chain.ainvoke({"query": query})
        
        # BACKGROUND METRICS: Log the cost of small talk without making the user wait.
        asyncio.create_task(_log_direct_metrics(llm, response))

        # FIX: Return 'final_output' to match your AgentState definition.
        return {"final_output": response.content}

    except Exception as e:
        log_error(f"❌ [Direct Response] failed: {e}")
        return {"final_output": "Hello! I'm ready to help with your financial regulation questions. What's on your mind?"}

async def _log_direct_metrics(llm, response):
    """Internal helper for background metrics tracking."""
    try:
        metadata = getattr(response, "response_metadata", {})
        usage = metadata.get("usage_metadata") or metadata.get("token_usage") or {}
        token_count = usage.get("total_tokens", 0)
        model_name = getattr(llm, "model", "gemini-2.5-flash")
        
        record_token_usage(model_name, "direct_response", token_count)
    except Exception:
        pass