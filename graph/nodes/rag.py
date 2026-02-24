#!/usr/bin/env python3
"""
Retrieval-Augmented Generation (RAG) Node - Tier 1 Optimized
Focuses on passing full Document objects for Synthesis Node compatibility.
"""

from typing import Any, Dict

from langchain_core.documents import Document

from graph.state import AgentState
from observability.logger import log_error, log_info, log_warning
from retrieval.hybrid_search import hybrid_search


async def retrieve_docs(state: AgentState) -> Dict[str, Any]:
    """
    Retrieve relevant documents using hybrid search.
    Returns Document objects to ensure compatibility with synthesis nodes.
    """
    query = state.get("query", "").strip()
    filters = state.get("filters", {}) or {}

    if not query:
        log_warning("⚠️ [RAG Node] Empty query. Skipping.")
        return {"retrieved_docs": []}

    log_info(f"🔍 [RAG Node] Searching: {query[:50]}... | Filters: {filters}")

    try:
        # Execute the optimized hybrid search
        docs = await hybrid_search(
            query=query,
            k=8,  # Reduced from 12 to 8 to manage token context window
            filters=filters,
        )

        if not docs:
            log_warning(f"📭 [RAG Node] No documents found for query: {query[:30]}")
            return {"retrieved_docs": []}

        # 🔹 PERFORMANCE: Ensure content is clean but preserve the Document type.
        # This prevents the Synthesis Node from failing when accessing .page_content
        for doc in docs:
            doc.page_content = doc.page_content.strip()
            # Ensure metadata isn't empty for the Reranker/Synthesizer
            if not doc.metadata:
                doc.metadata = {"source": "Unknown"}

        log_info(f"✅ [RAG Node] Retrieved {len(docs)} Document objects")

        # We return the objects directly. LangGraph handles the state.
        return {"retrieved_docs": docs}

    except Exception as e:
        log_error(f"❌ [RAG Node] Failed: {e}")
        return {"retrieved_docs": []}
