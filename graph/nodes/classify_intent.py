# graph/nodes/classify_intent.py
"""
Intent Classification Node - Tier 1 Production Optimized.
Includes Keyword Heuristics to survive LLM 503/Timeout errors.
"""

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

from app.llm_config import get_llm
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from observability.logger import log_error, log_info, log_warning
from observability.metrics import record_token_usage


# 1. Define the schema
class IntentSchema(BaseModel):
    category: Literal[
        "regulatory_lookup", "calculation", "reasoning", "structured", "other"
    ] = Field(description="The classified intent of the user query")


def _get_heuristic_intent(query: str) -> str:
    q = query.lower()

    regulatory_words = [
        "basel",
        "bcbs",
        "cftc",
        "sec",
        "federal reserve",
        "fed",
        "fomc",
        "rule",
        "regulation",
        "regulatory",
        "guidance",
        "policy",
        "framework",
        "press release",
        "speech",
        "testimony",
        "minutes",
        "transcript",
        "statement",
        "projections",
        "meeting",
        "document",
        "filing",
        "enforcement",
    ]
    if any(w in q for w in regulatory_words):
        return "regulatory_lookup"

    if any(word in q for word in ["why", "compare", "impact", "explain"]):
        return "reasoning"

    return "other"


async def classify_intent(state: AgentState) -> Dict[str, Any]:
    query = state.get("query", "").strip()
    log_info(f"[Classify Node] Analyzing query: {query[:80]}...")

    # Pre-calculate fallback in case of API failure
    fallback_intent = _get_heuristic_intent(query)

    try:
        llm = get_llm()

        # 2. Structured output with safety
        structured_llm = llm.with_structured_output(IntentSchema, include_raw=True)

        classify_prompt = load_prompt("classify_intent")

        # Execution
        response = await (classify_prompt | structured_llm).ainvoke({"query": query})

        # 3. Parsing
        parsed_output = response.get("parsed")
        raw_message = response.get("raw")

        if parsed_output and hasattr(parsed_output, "category"):
            intent = parsed_output.category
        else:
            log_warning("LLM returned success but failed parsing. Using heuristic.")
            intent = fallback_intent

        # 4. Token logging
        try:
            metadata = getattr(raw_message, "response_metadata", {}) or {}
            token_usage = (
                metadata.get("usage_metadata") or metadata.get("token_usage") or {}
            )
            token_count = token_usage.get("total_tokens", 0)

            current_model = getattr(llm, "model", "unknown-model")

            record_token_usage(
                model=current_model,
                component="classify_intent",
                token_count=token_count,
            )
            log_info(f"✅ Classified intent: {intent} (Tokens: {token_count})")
        except Exception as metrics_err:
            log_error(f"Metrics logging failed: {metrics_err}")

        return {"intent": intent}

    except Exception as e:
        log_error(f"❌ Classification API failure: {e}")
        log_info(f"⚠️ Resilience: Falling back to heuristic intent: {fallback_intent}")
        return {"intent": fallback_intent}
