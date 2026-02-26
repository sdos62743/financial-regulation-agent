#!/usr/bin/env python3
"""
Corrective RAG (CRAG) - Retrieval quality gate and decompose-then-recompose.

Implements:
1. Retrieval Evaluator: Assesses doc quality → correct | ambiguous | incorrect
2. Decompose-then-Recompose: Filters irrelevant content from docs when ambiguous
3. Reject path: Returns safe clarification when retrieval is incorrect
"""

from typing import Any, Dict, List

from langchain_core.documents import Document

from app.llm_config import get_llm
from graph.constants import SAFE_CLARIFICATION_MSG
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from observability.logger import log_error, log_info, log_warning


def _get_docs_preview(docs: List[Any], max_chars: int = 2500) -> str:
    """Build a short preview of retrieved docs for the evaluator."""
    if not docs:
        return "(No documents retrieved)"
    parts = []
    total = 0
    for i, doc in enumerate(docs[:6]):
        content = getattr(doc, "page_content", "") or ""
        preview = content[:500].replace("\n", " ")
        source = "Unknown"
        if hasattr(doc, "metadata") and doc.metadata:
            source = (
                doc.metadata.get("url")
                or doc.metadata.get("source")
                or doc.metadata.get("title", "Unknown")
            )
        parts.append(f"[Doc {i + 1} | {source}]: {preview}...")
        total += len(parts[-1])
        if total >= max_chars:
            break
    return "\n\n".join(parts)


async def evaluate_retrieval(state: AgentState) -> Dict[str, Any]:
    """
    CRAG Retrieval Evaluator: Assess quality of retrieved documents.
    Returns retrieval_confidence: "correct" | "ambiguous" | "incorrect"
    """
    query = state.get("query", "").strip()
    docs = state.get("retrieved_docs") or []

    if not query:
        return {"retrieval_confidence": "incorrect"}

    if not docs:
        log_warning("📭 [CRAG] No documents → incorrect")
        return {"retrieval_confidence": "incorrect"}

    docs_preview = _get_docs_preview(docs)

    try:
        llm = get_llm()
        prompt = load_prompt("crag_evaluator")
        chain = prompt | llm
        response = await chain.ainvoke({"query": query, "docs_preview": docs_preview})
        raw = (response.content or "").strip().lower()
        if "correct" in raw:
            confidence = "correct"
        elif "ambiguous" in raw:
            confidence = "ambiguous"
        else:
            confidence = "incorrect"

        log_info(f"📊 [CRAG] Retrieval confidence: {confidence}")
        return {"retrieval_confidence": confidence}
    except Exception as e:
        log_error(f"❌ [CRAG] Evaluator failed: {e}")
        return {"retrieval_confidence": "correct"}  # Fail open


async def decompose_recompose(state: AgentState) -> Dict[str, Any]:
    """
    Decompose-then-Recompose: Extract key info from each doc relevant to the query.
    Replaces retrieved_docs with refined Document objects.
    """
    query = state.get("query", "").strip()
    docs = state.get("retrieved_docs") or []

    if not docs or not query:
        return {}

    log_info(f"🔬 [CRAG] Decompose-recompose on {len(docs)} docs")

    llm = get_llm()
    prompt = load_prompt("crag_decompose")
    chain = prompt | llm

    refined: List[Document] = []
    for doc in docs[:6]:
        content = getattr(doc, "page_content", "") or ""
        metadata = getattr(doc, "metadata", {}) or {}
        source = (
            metadata.get("url")
            or metadata.get("source")
            or metadata.get("title", "Regulatory Document")
        )

        if len(content) < 100:
            refined.append(doc)
            continue

        try:
            response = await chain.ainvoke(
                {"query": query, "content": content[:3000], "source": source}
            )
            new_content = (response.content or "").strip()
            if new_content and "no relevant content" not in new_content.lower():
                refined.append(Document(page_content=new_content, metadata=metadata))
            else:
                refined.append(doc)
        except Exception as e:
            log_warning(f"[CRAG] Decompose failed for doc: {e}")
            refined.append(doc)

    log_info(f"✅ [CRAG] Refined {len(refined)} documents")
    return {"refined_docs": refined}


def crag_reject(state: AgentState) -> Dict[str, Any]:
    """
    CRAG Reject: Retrieval was incorrect. Return safe clarification.
    """
    log_info("🚫 [CRAG] Rejecting - retrieval quality insufficient")
    return {
        "final_output": SAFE_CLARIFICATION_MSG,
        "synthesized_response": "",
    }
