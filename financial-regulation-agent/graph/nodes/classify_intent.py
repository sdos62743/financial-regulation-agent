# graph/nodes/classify_intent.py
"""
Intent Classification Node - Validated for 2026 Structured Outputs.
"""

from typing import Literal, Dict, Any
from pydantic import BaseModel, Field

from observability.logger import log_error, log_info
from observability.metrics import record_token_usage 
from graph.state import AgentState
from graph.prompts.loader import load_prompt
from app.llm_config import get_llm

# 1. Define the schema (unchanged - this is good)
class IntentSchema(BaseModel):
    category: Literal["regulatory_lookup", "calculation", "reasoning", "structured", "other"] = Field(
        description="The classified intent of the user query"
    )

async def classify_intent(state: AgentState) -> Dict[str, Any]:
    query = state.get("query", "").strip()
    log_info(f"[Classify Node] Analyzing query: {query[:80]}...")

    try:
        llm = get_llm()
        
        # 2. Structured output with safety
        structured_llm = llm.with_structured_output(IntentSchema, include_raw=True)

        classify_prompt = load_prompt("classify_intent")

        response = await (classify_prompt | structured_llm).ainvoke({"query": query})
        
        # Safe parsing with fallback
        parsed_output = response.get("parsed") or response
        raw_message = response.get("raw") or response

        intent = parsed_output.category if hasattr(parsed_output, "category") else "other"

        # 3. Token logging (your original logic preserved)
        metadata = getattr(raw_message, "response_metadata", {}) or {}
        token_usage = metadata.get("token_usage") or metadata.get("usage_metadata") or {}
        token_count = token_usage.get("total_tokens", 0)
        
        current_model = getattr(llm, "model", "unknown-model")
        
        record_token_usage(
            model=current_model,
            component="classify_intent",
            token_count=token_count
        )

        log_info(f"✅ Classified intent: {intent} (Tokens: {token_count})")

        return {"intent": intent}

    except Exception as e:
        log_error(f"Classification failed: {e}", exc_info=True)
        # Safe fallback
        return {"intent": "other"}