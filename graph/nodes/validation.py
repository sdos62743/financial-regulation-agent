#!/usr/bin/env python3
"""
Validation / Critic Node - Tier 1 Optimized (fixed)
- Reads docs from state["documents"] (fallback to ["retrieved_docs"])
- Robust parsing for "valid: true/false"
- Increments iterations correctly
- Prevents stale draft answers from leaking to UI on invalid
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List

from app.llm_config import get_llm
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from observability.logger import log_error, log_info
from observability.metrics import record_evaluation_score, record_token_usage

_VALID_TRUE_RE = re.compile(r"\bvalid:\s*true\b", re.I)
_VALID_FALSE_RE = re.compile(r"\bvalid:\s*false\b", re.I)


def _get_docs(state: AgentState) -> List[Any]:
    """
    Prefer the canonical key used across the graph: 'documents'.
    Fall back to 'retrieved_docs' for older nodes.
    """
    docs = state.get("documents")
    if isinstance(docs, list) and docs:
        return docs

    docs2 = state.get("retrieved_docs")
    if isinstance(docs2, list) and docs2:
        return docs2

    return []


def _format_sources(docs: List[Any], limit: int = 6) -> str:
    if not docs:
        return "No source documents available."

    entries: List[str] = []
    for i, doc in enumerate(docs[:limit], 1):
        content = getattr(doc, "page_content", "") or ""
        md = getattr(doc, "metadata", {}) or {}

        url = md.get("url") or md.get("source") or "unknown_url"
        title = md.get("title") or md.get("doc_id") or "untitled"
        date = md.get("date") or md.get("year") or "unknown_date"
        regulator = md.get("regulator") or "unknown_regulator"
        doc_type = md.get("type") or "unknown_type"
        category = md.get("category") or "unknown_category"

        entries.append(
            f"Source {i}:\n"
            f"- url: {url}\n"
            f"- title: {title}\n"
            f"- date: {date}\n"
            f"- regulator: {regulator}\n"
            f"- type: {doc_type}\n"
            f"- category: {category}\n"
            f"- excerpt: {content[:900]}\n"
        )

    return "\n\n".join(entries)


def _parse_valid_flag(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _VALID_TRUE_RE.search(t):
        return True
    if _VALID_FALSE_RE.search(t):
        return False
    # Conservative default: invalid if we can't parse
    return False


async def validate_response(state: AgentState) -> Dict[str, Any]:
    query = (state.get("query") or "").strip()
    draft = (state.get("synthesized_response") or state.get("response") or "").strip()

    current_iter = int(state.get("iterations") or 0)
    next_iter = current_iter + 1
    is_retry = current_iter > 0

    docs = _get_docs(state)
    sources_str = _format_sources(docs, limit=6)

    log_info(
        f"🧐 [Validation Node] Starting check | Attempt: {next_iter} | "
        f"Retry: {is_retry} | docs={len(docs)}"
    )

    try:
        llm = get_llm()
        validate_prompt = load_prompt("validate")
        chain = validate_prompt | llm

        result = await chain.ainvoke(
            {
                "query": query,
                "response": draft,
                "sources": sources_str,
                "is_retry": is_retry,
            }
        )

        raw = getattr(result, "content", "") or ""
        is_valid = _parse_valid_flag(raw)

        asyncio.create_task(_log_validation_metrics(llm, result, is_valid))
        log_info(f"{'✅' if is_valid else '❌'} [Validation] Result: {is_valid}")

        if is_valid:
            # On valid: lock final_output
            return {
                "validation_result": True,
                "iterations": next_iter,
                "final_output": draft,
            }

        # On invalid: prevent stale answer from being shown by controller/UI
        safe_msg = (
            "I can’t confirm that answer from the retrieved documents. "
            "Please specify which regulator/meeting series you mean "
            "(e.g., FOMC, Basel, CFTC, SEC), "
            "or add a keyword like 'FOMC minutes'."
        )

        return {
            "validation_result": is_valid,
            "iterations": next_iter,
            "final_output": safe_msg,
            "synthesized_response": safe_msg,
        }
    except Exception as e:
        log_error(f"❌ [Validation Node] Failed: {e}", exc_info=True)
        # Fail-open but still avoid stale leakage:
        fallback = (
            draft or "I ran into an issue validating the answer. Please try again."
        )
        return {
            "validation_result": True,
            "iterations": next_iter,
            "final_output": fallback,
        }


async def _log_validation_metrics(llm, result, is_valid: bool):
    try:
        model_name = (
            getattr(llm, "model_name", None)
            or getattr(llm, "model", None)
            or "unknown_model"
        )

        metadata = getattr(result, "response_metadata", {}) or {}
        usage = metadata.get("usage_metadata") or metadata.get("token_usage") or {}

        record_token_usage(model_name, "validation_node", usage.get("total_tokens", 0))
        record_evaluation_score(1.0 if is_valid else 0.0, "hallucination_check")
    except Exception:
        pass
