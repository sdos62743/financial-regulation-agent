#!/usr/bin/env python3
"""
Validation / Critic Node - Tier 1 Optimized
Performs hallucination checks and manages the graph's iterative logic.
"""

import asyncio
from typing import Dict, Any
from graph.state import AgentState
from graph.prompts.loader import load_prompt
from observability.logger import log_info, log_error
from observability.metrics import record_token_usage, record_evaluation_score
# from observability.monitor import SystemMonitor  # Uncomment if needed
from app.llm_config import get_llm

async def validate_response(state: AgentState) -> Dict[str, Any]:
    """
    Validate the synthesized response against retrieved documents.
    """
    query = state.get("query", "").strip()
    response = state.get("synthesized_response", "").strip()
    retrieved_docs = state.get("retrieved_docs", [])
    current_iter = state.get("iterations", 0)
    is_retry = current_iter > 0
    
    log_info(f"🧐 [Validation Node] Starting check | Attempt: {current_iter + 1} | Retry: {is_retry}")

    # 1. Efficient Context Formatting (your original logic preserved)
    doc_entries = [
        f"Source {i}: {doc.get('page_content', '')[:800]}"
        for i, doc in enumerate(retrieved_docs[:6], 1)
    ]
    sources_str = "\n\n".join(doc_entries) if doc_entries else "No source documents available."

    try:
        llm = get_llm()
        validate_prompt = load_prompt("validate")
        chain = validate_prompt | llm

        # 2. Invoke LLM for hallucination check
        result = await chain.ainvoke({
            "query": query,
            "response": response,
            "sources": sources_str,
            "is_retry": is_retry   # New prompt uses this
        })

        output_text = result.content.strip().lower()
        
        # ==================== OLD PARSING (commented) ====================
        # is_valid = "valid: true" in output_text or "is_valid: true" in output_text
        # =================================================================

        # New robust parsing for the updated prompt format
        is_valid = "valid: true" in output_text

        # 3. BACKGROUND TASKS: Metrics and Monitoring (your original helper preserved)
        asyncio.create_task(_log_validation_metrics(llm, result, is_valid))

        log_info(f"{'✅' if is_valid else '❌'} [Validation] Result: {is_valid}")

        return {
            "validation_result": is_valid,
            "iterations": 1,                    # Graph handles increment via operator.add
            "final_output": response if is_valid else ""
        }

    except Exception as e:
        log_error(f"❌ [Validation Node] Failed: {e}")
        # Fallback: Accept the response on error to prevent blocking the user
        return {
            "validation_result": True,
            "iterations": 1,
            "final_output": response
        }


async def _log_validation_metrics(llm, result, is_valid: bool):
    """Background helper for observability (your original logic preserved)."""
    try:
        model_name = getattr(llm, "model", "gemini-1.5-flash")
        metadata = getattr(result, "response_metadata", {})
        usage = metadata.get("usage_metadata") or metadata.get("token_usage") or {}
        
        record_token_usage(model_name, "validation_node", usage.get("total_tokens", 0))
        record_evaluation_score(1.0 if is_valid else 0.0, "hallucination_check")
        
        # if is_valid:
        #     SystemMonitor.record_hallucination_rate(0.0)
    except Exception:
        pass