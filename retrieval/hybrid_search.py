#!/usr/bin/env python3
"""
Hybrid Search Engine - Tier 1 Production Optimized
Uses Manual RRF and Cohere Reranking.
Fixes ChromaDB multi-filter syntax using $and operator.
"""

import asyncio
import os
from collections import defaultdict
from typing import Any, Dict, List, Optional

from langchain_cohere import CohereRerank
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from app.llm_config import get_embeddings
from observability.logger import log_error, log_info, log_warning

from .vector_store import get_vector_store

DEFAULT_TOP_K = int(os.getenv("HYBRID_TOP_K", 8))
DEFAULT_BM25_WEIGHT = float(os.getenv("HYBRID_BM25_WEIGHT", 0.4))
DEFAULT_VECTOR_WEIGHT = float(os.getenv("HYBRID_VECTOR_WEIGHT", 0.6))
RRF_K = 60


def _normalize_list(val: Any) -> Optional[List[Any]]:
    """Ensures input for $in operator is always a non-empty list."""
    if val is None:
        return None
    if isinstance(val, list):
        return val if len(val) > 0 else None
    return [val]


async def apply_rrf(
    vector_results: List[Document],
    bm25_results: List[Document],
    weights: List[float],
    limit: int,
) -> List[Document]:
    rrf_score: Dict[str, float] = defaultdict(float)
    doc_map: Dict[str, Document] = {}

    for docs, weight in zip([bm25_results, vector_results], weights):
        for rank, doc in enumerate(docs, start=1):
            # Use content and metadata for unique ID to avoid duplicates in fusion
            doc_id = f"{doc.page_content[:100]}_{doc.metadata.get('source', '')}"
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
    filters: Optional[Dict[str, Any]] = None,
) -> List[Document]:
    top_k = k or DEFAULT_TOP_K
    bw = bm25_weight or DEFAULT_BM25_WEIGHT
    vw = vector_weight or DEFAULT_VECTOR_WEIGHT

    log_info(f"🔎 [Hybrid Search] Query: {query[:60]}... | Filters: {filters}")

    try:
        store = get_vector_store()
        # 1. Build Filtered Search Args with Chroma Logical Operators
        search_kwargs = {"k": top_k * 4}
        chroma_filter = {}

        if filters:
            conditions = []

            # Regulator Filter
            regs = _normalize_list(filters.get("regulators"))
            if regs:
                conditions.append({"regulator": {"$in": regs}})

            # Doc Type Filter
            dts = _normalize_list(filters.get("doc_types"))
            if dts:
                conditions.append({"type": {"$in": dts}})

            # Year Filter (Integer Conversion)
            year = filters.get("year")
            if year:
                try:
                    conditions.append({"year": int(year)})
                except (ValueError, TypeError):
                    log_warning(f"⚠️ Invalid year filter: {year}")

            # Jurisdiction Filter
            if filters.get("jurisdiction"):
                conditions.append({"jurisdiction": filters["jurisdiction"]})

            # 🔹 FIXED: Chroma requires $and for multiple conditions
            if len(conditions) > 1:
                chroma_filter = {"$and": conditions}
            elif len(conditions) == 1:
                chroma_filter = conditions[0]

            if chroma_filter:
                search_kwargs["filter"] = chroma_filter
                log_info(f"🎯 Chroma Filter: {chroma_filter}")

        # 2. Vector Retrieval
        vector_retriever = store.as_retriever(search_kwargs=search_kwargs)

        # 3. Filtered Data for BM25
        # We fetch docs matching the filter to ensure BM25 stays relevant
        if chroma_filter:
            filtered_data = store.get(where=chroma_filter)
        else:
            filtered_data = store.get(limit=500)

        if not filtered_data or not filtered_data.get("documents"):
            log_warning("📭 No docs match filters. Returning vector-only results.")
            return await vector_retriever.ainvoke(query)

        all_docs = [
            Document(page_content=c, metadata=m or {})
            for c, m in zip(
                filtered_data["documents"], filtered_data.get("metadatas", [])
            )
        ]

        # 4. Perform Parallel Retrieval
        bm25_retriever = BM25Retriever.from_documents(documents=all_docs)
        bm25_retriever.k = top_k * 4

        bm25_results, vector_results = await asyncio.gather(
            bm25_retriever.ainvoke(query), vector_retriever.ainvoke(query)
        )

        # 5. Reciprocal Rank Fusion
        fused_results = await apply_rrf(
            vector_results, bm25_results, [bw, vw], top_k * 4
        )

        # 6. Cohere Reranking
        cohere_key = os.getenv("COHERE_API_KEY")
        if use_reranker and cohere_key and fused_results:
            try:
                reranker = CohereRerank(model="rerank-english-v3.0", top_n=top_k)
                return reranker.compress_documents(fused_results, query)
            except Exception as e:
                log_error(f"Reranker failed: {e}")
                return fused_results[:top_k]

        return fused_results[:top_k]

    except Exception as e:
        log_error(f"❌ Hybrid search failure: {e}", exc_info=True)
        return []
