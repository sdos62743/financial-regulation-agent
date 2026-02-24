import asyncio
import json
from typing import Any, Dict

from observability.logger import log_error, log_info, log_warning
from observability.metrics import record_token_usage
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from app.llm_config import get_llm

# 🔹 Tier 1: General Domain Keywords
# Add any regulators you support here
SUPPORTED_REGULATORS = ["BASEL", "SEC", "CFTC", "FED", "FINCEN", "FCA", "FDIC"]

def _heuristic_filter_extraction(query: str) -> Dict[str, Any]:
    """General keyword-based extraction as a safety net."""
    q = query.upper()
    found_regs = [reg for reg in SUPPORTED_REGULATORS if reg in q]
    
    return {
        "regulators": found_regs if found_regs else None,
        "year": None, # Hard to parse reliably with regex
        "doc_types": None,
        "jurisdiction": "US" if " US " in q or "USA" in q else None
    }

async def extract_filters(state: AgentState) -> Dict[str, Any]:
    query = state.get("query", "").strip()
    log_info(f"🔍 [Extract Filters] Analyzing: {query[:60]}...")

    try:
        llm = get_llm()
        filter_prompt = load_prompt("extract_filters")
        chain = filter_prompt | llm

        response = await chain.ainvoke({"query": query})
        result_text = response.content.strip()

        # Parse JSON
        try:
            # Strip potential markdown backticks
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            
            filters = json.loads(result_text)
        except json.JSONDecodeError:
            log_warning("JSON Parse failed, using heuristics.")
            filters = _heuristic_filter_extraction(query)

        # Normalize keys
        cleaned_filters = {
            "regulators": filters.get("regulators") or filters.get("regulator"),
            "year": filters.get("year"),
            "doc_types": filters.get("doc_types") or filters.get("type"),
            "jurisdiction": filters.get("jurisdiction"),
        }

        # 🔹 Metrics (Fixed: ensured it's not a leaked coroutine)
        asyncio.create_task(_log_filter_metrics(llm, response))

        return {"filters": cleaned_filters}

    except Exception as e:
        log_error(f"❌ Filter Extraction API Error: {e}")
        # Return general heuristic instead of empty dict
        return {"filters": _heuristic_filter_extraction(query)}

async def _log_filter_metrics(llm, response):
    try:
        model_name = getattr(llm, "model", "gemini-1.5-flash")
        metadata = getattr(response, "response_metadata", {}) or {}
        usage = metadata.get("usage_metadata") or {}
        token_count = usage.get("total_tokens", 0)
        record_token_usage(model_name, "extract_filters", token_count)
    except Exception:
        pass