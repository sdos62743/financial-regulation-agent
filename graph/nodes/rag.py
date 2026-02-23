#!/usr/bin/env python3
"""
Retrieval-Augmented Generation (RAG) Node - Tier 1 Optimized
Focuses on state size management and efficient serialization.
Now passes extracted filters to hybrid_search.
"""

from typing import Dict, Any, List
from observability.logger import log_error, log_info, log_warning
from retrieval.hybrid_search import hybrid_search
from graph.state import AgentState

async def retrieve_docs(state: AgentState) -> Dict[str, Any]:
    """
    Retrieve relevant documents using hybrid search with optional metadata filters.
    """
    query = state.get("query", "").strip()
    filters = state.get("filters", {}) or {}   # ← New: Read filters from state

    if not query:
        log_warning("⚠️ [RAG Node] Empty query. Skipping.")
        return {"retrieved_docs": []}

    log_info(f"🔍 [RAG Node] Searching for: {query[:50]}... | Filters: {filters}")

    try:
        # Pass filters to hybrid_search (this is the key integration point)
        docs = await hybrid_search(
            query=query,
            k=12,
            filters=filters   # ← New line
        )

        if not docs:
            log_warning(f"📭 [RAG Node] No documents found for query: {query[:30]}")
            return {"retrieved_docs": []}

        # PERFORMANCE: Manual Serialization (your original logic preserved)
        serialized_docs = [
            {
                "page_content": doc.page_content.strip(),
                "metadata": {
                    "source": doc.metadata.get("source", "Unknown"),
                    "page": doc.metadata.get("page", 0),
                    "score": doc.metadata.get("score", 0.0)
                }
            }
            for doc in docs
        ]

        log_info(f"✅ [RAG Node] Retrieved {len(serialized_docs)} docs")
        
        return {"retrieved_docs": serialized_docs}

    except Exception as e:
        log_error(f"❌ [RAG Node] Failed: {e}")
        return {"retrieved_docs": []}