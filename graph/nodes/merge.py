#!/usr/bin/env python3
"""
Synthesis / Merge Node - Tier 1 Optimized
Combines parallel outputs into a coherent final response.
"""

import asyncio
from typing import Dict, Any
from observability.logger import log_error, log_info
from observability.metrics import record_evaluation_score, record_token_usage
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from app.llm_config import get_llm

async def merge_outputs(state: AgentState) -> Dict[str, Any]:
    """
    Synthesize the final response.
    """
    query = state.get("query", "").strip()
    plan = state.get("plan", [])
    retrieved_docs = state.get("retrieved_docs", [])
    tool_outputs = state.get("tool_outputs", [])

    log_info(f"🧬 [Merge Node] Synthesizing final response for query: {query[:50]}...")

    # 1. Format Context (your original logic preserved)
    plan_str = "\n".join(plan) if plan else "No plan generated."
    
    doc_entries = []
    for i, doc in enumerate(retrieved_docs[:8], 1):
        content = doc.get("page_content", "")
        meta = doc.get("metadata", {})
        source = meta.get("source", "Regulatory Document")
        doc_entries.append(f"Document {i} [{source}]:\n{content[:1200]}")
    
    docs_str = "\n\n".join(doc_entries) if doc_entries else "No documents available."

    tools_str = (
        "\n\n".join(str(output) for output in tool_outputs)
        if tool_outputs else "No tool results."
    )

    try:
        llm = get_llm()
        prompt_template = load_prompt("merge")
        
        chain = prompt_template | llm

        response = await chain.ainvoke({
            "query": query, 
            "plan": plan_str, 
            "docs": docs_str, 
            "tools": tools_str
        })

        final_response = response.content.strip()

        # Clean up common extra text from Gemini (new defensive step)
        if "Final Response:" in final_response:
            final_response = final_response.split("Final Response:")[-1].strip()

        # 4. BACKGROUND TASKS (your original helper preserved)
        asyncio.create_task(_record_merge_metrics(llm, response))

        return {"synthesized_response": final_response}

    except Exception as e:
        log_error(f"❌ [Merge Node] Failure: {e}", exc_info=True)
        return {
            "synthesized_response": "I encountered an error while preparing the final analysis. Please try again."
        }


async def _record_merge_metrics(llm, response):
    """Internal helper to log usage metadata in the background."""
    try:
        model_name = getattr(llm, "model", "gemini-1.5-flash")
        
        metadata = getattr(response, "response_metadata", {})
        usage = metadata.get("usage_metadata") or metadata.get("token_usage") or {}
        token_count = usage.get("total_tokens", 0)
        
        record_token_usage(model_name, "merge_node", token_count)
        record_evaluation_score(0.85, "synthesis")
        
        log_info(f"✅ [Merge Node] Completed | {token_count} tokens used")
    except Exception:
        pass