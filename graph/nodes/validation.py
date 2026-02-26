#!/usr/bin/env python3
"""
Validation / Critic Node - Tier 1 Optimized (fixed)
- Reads docs from state["retrieved_docs"] (canonical key used by RAG node)
- Robust parsing for "valid: true/false"
- Increments iterations correctly
- Prevents stale draft answers from leaking to UI on invalid
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Set

from pydantic import BaseModel, Field

from app.llm_config import get_llm
from graph.constants import SAFE_CLARIFICATION_MSG
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from observability.logger import log_error, log_info
from observability.metrics import record_evaluation_score, record_token_usage


class ValidationResult(BaseModel):
    """Structured output from the validation critic."""

    valid: bool = Field(description="True if response is sufficiently supported by sources.")
    reason: str = Field(description="One sentence explaining the decision.")


def _get_docs(state: AgentState) -> List[Any]:
    """Read documents from state['retrieved_docs'] (set by RAG node)."""
    docs = state.get("retrieved_docs")
    if isinstance(docs, list) and docs:
        return docs
    return []


def _extract_cited_urls(text: str) -> Set[str]:
    """Extract URLs and URL path fragments (e.g. 9070-25) from response."""
    found: Set[str] = set()
    # Full URLs
    for m in re.finditer(r"https?://[^\s\)\]\"']+", text or ""):
        url = m.group(0).rstrip(".,;:)")
        found.add(url)
        # Also add path-like fragment for matching (e.g. 9070-25, 9037-25)
        parts = re.findall(r"[\w-]+-\d{2,}", url)
        found.update(parts)
    # Standalone release numbers (e.g. 9070-25, Press Release 9070-25)
    for m in re.finditer(r"(?:Press\s*Release\s*|Release\s*#?\s*)?(\d{4,5}-\d{2})", text or "", re.I):
        found.add(m.group(1))
    return found


def _get_source_urls(docs: List[Any]) -> Set[str]:
    """Get URLs and path fragments from doc metadata for matching."""
    urls: Set[str] = set()
    for doc in docs or []:
        md = getattr(doc, "metadata", {}) or {}
        url = md.get("url") or md.get("source") or ""
        if url:
            urls.add(url)
            parts = re.findall(r"[\w-]+-\d{2,}", url)
            urls.update(parts)
    return urls


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

    retry_note = (
        "**Note: This is a RETRY.** Be slightly more lenient."
        if is_retry
        else "Apply standard strictness."
    )

    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(ValidationResult, include_raw=True)
        validate_prompt = load_prompt("validate")
        chain = validate_prompt | structured_llm

        response = await chain.ainvoke(
            {
                "query": query,
                "response": draft,
                "sources": sources_str,
                "retry_note": retry_note,
            }
        )

        parsed = response.get("parsed") or response
        if isinstance(parsed, ValidationResult):
            is_valid = parsed.valid
            reason = parsed.reason or ""
        else:
            is_valid = False
            reason = ""

        raw = response.get("raw") or response
        asyncio.create_task(_log_validation_metrics(llm, raw, is_valid))

        # Override false negative: critic says "not in sources" but cited URLs are in docs
        cited = _extract_cited_urls(draft)
        source_urls = _get_source_urls(docs)
        if cited and source_urls:
            cited_in_sources = cited & source_urls
            not_in_sources = cited - source_urls
            rejection_phrases = ("not in", "not present", "not included", "not in the provided")
            reason_lower = (reason or "").lower()
            if (
                not is_valid
                and any(p in reason_lower for p in rejection_phrases)
                and not not_in_sources
            ):
                is_valid = True
                reason = "Cited documents are in the provided sources."
                log_info(f"✅ [Validation] Override: cited URLs {cited_in_sources} are in sources")

        log_info(f"{'✅' if is_valid else '❌'} [Validation] Result: {is_valid}")

        if is_valid:
            # On valid: lock final_output
            return {
                "validation_result": True,
                "iterations": next_iter,
                "final_output": draft,
            }

        # On invalid: prevent stale answer, pass feedback to planner for retry
        return {
            "validation_result": is_valid,
            "iterations": next_iter,
            "final_output": SAFE_CLARIFICATION_MSG,
            "synthesized_response": SAFE_CLARIFICATION_MSG,
            "validation_feedback": reason,
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
