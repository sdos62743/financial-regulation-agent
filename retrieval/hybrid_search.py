#!/usr/bin/env python3
"""
Hybrid Search Engine - Tier 1 Production Optimized
Uses Manual RRF and Cohere Reranking.
Now supports metadata filtering from extract_filters node.
"""

import os
import asyncio
from typing import Any, Dict, List, Optional
from collections import defaultdict

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from langchain_cohere import CohereRerank

from observability.logger import log_info, log_warning, log_error
from app.llm_config import get_embeddings
from .vector_store import get_vector_store

# Tier 1 Default Settings
DEFAULT_TOP_K = int(os.getenv("HYBRID_TOP_K", 8))
DEFAULT_BM25_WEIGHT = float(os.getenv("HYBRID_BM25_WEIGHT", 0.4))
DEFAULT_VECTOR_WEIGHT = float(os.getenv("HYBRID_VECTOR_WEIGHT", 0.6))
RRF_K = 60


async def apply_rrf(
    vector_results: List[Document], 
    bm25_results: List[Document], 
    weights: List[float], 
    limit: int
) -> List[Document]:
    """Manual Reciprocal Rank Fusion (your original logic preserved)."""
    rrf_score: Dict[str, float] = defaultdict(float)
    doc_map: Dict[str, Document] = {}

    for docs, weight in zip([bm25_results, vector_results], weights):
        for rank, doc in enumerate(docs, start=1):
            doc_id = doc.page_content.strip()
            if doc_id not in doc_map:
                doc_map[doc_id] = doc
            rrf_score[doc_id] += weight * (1.0 / (RRF_K + rank))

    sorted_docs = sorted(rrf_score.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[doc_id] for doc_id, _ in sorted_docs[:limit]]


async def hybrid_search(
    query: str,
    k: Optional[int] = None,
    bm25_weight: Optional[float] = None,
    vector_weight: Optional[float] = None,
    use_reranker: bool = True,
    filters: Optional[Dict[str, Any]] = None,   # Accepts filters from extract_filters node
) -> List[Document]:
    """
    Hybrid Search with optional metadata filtering.
    """
    top_k = k or DEFAULT_TOP_K
    bw = bm25_weight or DEFAULT_BM25_WEIGHT
    vw = vector_weight or DEFAULT_VECTOR_WEIGHT

    log_info(f"🔎 [Hybrid Search] Query: {query[:60]}... | Filters: {filters}")

    embeddings = get_embeddings()
    store = get_vector_store(embeddings=embeddings)

    try:
        # ==================== NEW: Apply Metadata Filtering ====================
        search_kwargs = {"k": top_k * 4}
        
        if filters and any(v is not None for v in filters.values()):
            chroma_filter = {}
            if filters.get("regulators"):
                chroma_filter["regulator"] = {"$in": filters["regulators"]}
            if filters.get("year"):
                chroma_filter["year"] = filters["year"]
            if filters.get("doc_types"):
                chroma_filter["type"] = {"$in": filters["doc_types"]}
            if filters.get("jurisdiction"):
                chroma_filter["jurisdiction"] = filters["jurisdiction"]
            
            search_kwargs["filter"] = chroma_filter
            log_info(f"Applying metadata filter: {chroma_filter}")
        # =====================================================================

        # Vector Search
        vector_retriever = store.as_retriever(search_kwargs=search_kwargs)

        # BM25 (Keyword) Search
        raw_data = store.get()
        if not raw_data or not raw_data.get("documents"):
            log_warning("Vector store empty, falling back to vector-only search.")
            return await vector_retriever.ainvoke(query)

        all_docs = [
            Document(page_content=c, metadata=m or {})
            for c, m in zip(raw_data["documents"], raw_data.get("metadatas", []))
        ]
        
        bm25_retriever = BM25Retriever.from_documents(documents=all_docs)
        bm25_retriever.k = top_k * 4

        # Parallel execution
        log_info("⚡ Executing parallel Vector and BM25 retrieval...")
        bm25_results, vector_results = await asyncio.gather(
            bm25_retriever.ainvoke(query),
            vector_retriever.ainvoke(query)
        )

        # Fusion
        fused_results = await apply_rrf(
            vector_results=vector_results,
            bm25_results=bm25_results,
            weights=[bw, vw],
            limit=top_k * 4
        )

        # Reranking (your original logic preserved)
        cohere_key = os.getenv("COHERE_API_KEY")
        if use_reranker and cohere_key and fused_results:
            try:
                reranker = CohereRerank(
                    model="rerank-english-v3.0", 
                    top_n=top_k,
                    cohere_api_key=cohere_key
                )
                log_info(f"🎯 Reranking {len(fused_results)} documents...")
                return reranker.compress_documents(fused_results, query)
            except Exception as e:
                log_error(f"Reranker failed: {e}. Falling back to RRF.")
                return fused_results[:top_k]

        return fused_results[:top_k]

    except Exception as e:
        log_error(f"❌ Hybrid search critical failure: {e}", exc_info=True)
        return []