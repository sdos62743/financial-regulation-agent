#!/usr/bin/env python3
"""
Structured Extraction Node - Tier 1 Optimized
"""

import asyncio
from typing import Any, Dict

from pydantic import BaseModel, Field

from app.llm_config import get_llm
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from observability.logger import log_error, log_info
from observability.metrics import record_token_usage


# Define expected output schema (makes output consistent)
class StructuredOutput(BaseModel):
    entities: list = Field(default_factory=list)
    summary: str = Field(default="")
    total_fines: int | None = Field(default=None)
    # Add more fields as needed over time


async def structured_extraction(state: AgentState) -> Dict[str, Any]:
    query = state.get("query", "").strip()
    retrieved_docs = state.get("retrieved_docs", [])

    log_info(f"📊 [Structured Node] Extraction started for: {query[:60]}...")

    doc_entries = []
    for i, doc in enumerate(retrieved_docs[:6], 1):
        content = doc.get("page_content", "")
        meta = doc.get("metadata", {})
        source = meta.get("source", "Unknown")
        date = meta.get("date", "N/A")
        doc_entries.append(f"Source {i} [{source} | {date}]:\n{content[:1200]}")

    docs_str = "\n\n".join(doc_entries) if doc_entries else "No documents available."

    try:
        llm = get_llm()
        prompt_template = load_prompt("structured")

        # Use structured output (more reliable than raw text)
        structured_llm = llm.with_structured_output(StructuredOutput, include_raw=True)

        response = await (prompt_template | structured_llm).ainvoke(
            {"query": query, "docs": docs_str}
        )

        parsed = response.get("parsed") or response

        # Background metrics (your original helper style)
        asyncio.create_task(_log_structured_metrics(llm, response))

        return {"tool_outputs": [{"structured_data": parsed.dict()}]}

    except Exception as e:
        log_error(f"❌ [Structured Node] Critical failure: {e}")
        return {"tool_outputs": [{"structured_data": {}}]}


async def _log_structured_metrics(llm, response):
    """Internal helper for background metrics."""
    try:
        model_name = getattr(llm, "model", "gemini-1.5-flash")
        raw_message = response.get("raw") or response
        metadata = getattr(raw_message, "response_metadata", {}) or {}
        usage = metadata.get("usage_metadata") or metadata.get("token_usage") or {}
        token_count = usage.get("total_tokens", 0)

        record_token_usage(model_name, "structured_node", token_count)
        log_info(f"✅ [Structured Node] Extraction complete | Tokens: {token_count}")
    except Exception:
        pass
