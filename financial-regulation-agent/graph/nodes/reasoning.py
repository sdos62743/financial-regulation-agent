#!/usr/bin/env python3
"""
Planning / Reasoning Node - Tier 1 Optimized
"""

import asyncio
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from observability.logger import log_error, log_info
from observability.metrics import record_token_usage
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from app.llm_config import get_llm

class ExecutionPlan(BaseModel):
    """Schema for a step-by-step agent execution plan."""
    steps: List[str] = Field(description="Sequential actions to take.")
    rationale: str = Field(description="Strategic explanation.")

async def generate_plan(state: AgentState) -> Dict[str, Any]:
    query = state.get("query", "").strip()
    intent = state.get("intent", "other")

    log_info(f"🧠 [Planning Node] Generating strategy for: {intent} | Query: {query[:60]}...")

    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(ExecutionPlan, include_raw=True)
        
        plan_prompt = load_prompt("plan")

        response = await (plan_prompt | structured_llm).ainvoke({
            "query": query, 
            "intent": intent
        })

        # ==================== OLD PARSING (commented) ====================
        # parsed_plan = response["parsed"]
        # =================================================================

        # More robust parsing (handles both structured and raw responses)
        parsed_plan = response.get("parsed") or response

        # Background metrics (your original helper preserved)
        asyncio.create_task(_log_planning_metrics(llm, response))

        return {
            "plan": parsed_plan.steps,
            "plan_rationale": parsed_plan.rationale
        }

    except Exception as e:
        log_error(f"❌ [Planning Node] Failed: {e}")
        
        return {
            "plan": ["General regulatory analysis and document retrieval"],
            "plan_rationale": "Fallback plan triggered due to processing error."
        }

async def _log_planning_metrics(llm, response):
    """Internal helper to process usage data without blocking the workflow."""
    try:
        raw_message = response.get("raw") or response
        model_name = getattr(llm, "model", "gemini-1.5-flash")
        metadata = getattr(raw_message, "response_metadata", {}) or {}
        usage = metadata.get("usage_metadata") or metadata.get("token_usage") or {}
        total_tokens = usage.get("total_tokens", 0)
        
        record_token_usage(model_name, "planning_node", total_tokens)
        log_info(f"✅ [Planning Node] Logic ready ({total_tokens} tokens)")
    except Exception:
        pass