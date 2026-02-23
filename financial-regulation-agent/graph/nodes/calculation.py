#!/usr/bin/env python3
"""
Calculation Node - Tier 1 Optimized
Performs numerical analysis with background metrics and efficient state updates.
"""

import asyncio
from typing import Any, Dict, List
from observability.logger import log_error, log_info
from observability.metrics import record_token_usage
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from app.llm_config import get_llm

async def perform_calculation(state: AgentState) -> Dict[str, Any]:
    """
    Execute financial or analytical calculation based on query and context.
    """
    query = state.get("query", "").strip()
    tool_outputs = state.get("tool_outputs", [])
    retrieved_docs = state.get("retrieved_docs", [])

    log_info(f"🔢 [Calculation Node] Starting analysis for: {query[:50]}...")

    # 1. Build Context String (your original logic preserved)
    data_parts: List[str] = []

    if tool_outputs:
        data_parts.append("=== Previous Tool Outputs ===")
        for i, output in enumerate(tool_outputs, 1):
            data_parts.append(f"Tool Result {i}:\n{str(output)[:600]}")

    if retrieved_docs:
        data_parts.append("=== Regulatory Context ===")
        for i, doc in enumerate(retrieved_docs[:6], 1):
            content = doc.get("page_content", "")
            meta = doc.get("metadata", {})
            date_str = meta.get("date", "Unknown Date")
            data_parts.append(f"Doc {i} [{date_str}]: {content[:800]}")

    data_str = "\n\n".join(data_parts) if data_parts else "No specific context available."

    try:
        llm = get_llm()
        calc_prompt = load_prompt("calculation")
        chain = calc_prompt | llm

        # Execution
        raw_response = await chain.ainvoke({"query": query, "data": data_str})
        result = raw_response.content.strip()

        # ==================== OLD PARSING (commented) ====================
        # result = raw_response.content.strip()
        # =================================================================

        # Clean up common extra text from Gemini
        if "Final Calculation Result:" in result:
            result = result.split("Final Calculation Result:")[-1].strip()

        # 3. BACKGROUND METRICS (your original helper preserved)
        asyncio.create_task(_log_calc_metrics(llm, raw_response))

        return {"tool_outputs": [{"calculation_result": result}]}

    except Exception as e:
        log_error(f"❌ [Calculation Node] Failed: {e}")
        return {"tool_outputs": [{"calculation_result": "Error: Calculation failed."}]}


async def _log_calc_metrics(llm, response):
    """Internal helper to log usage without blocking node exit."""
    try:
        model_name = getattr(llm, "model", "gemini-1.5-flash")
        metadata = getattr(response, "response_metadata", {})
        usage = metadata.get("usage_metadata") or metadata.get("token_usage") or {}
        token_count = usage.get("total_tokens", 0)
        
        record_token_usage(model_name, "calculation_node", token_count)
        log_info(f"✅ [Calculation Node] Finished | Tokens: {token_count}")
    except Exception:
        pass