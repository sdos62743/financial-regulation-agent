#!/usr/bin/env python3
"""
Hybrid Search Engine - All Regulators (Approach A only)

Schema (strict, stored in Chroma metadata):
- regulator: str
- category: str (semantic: policy/enforcement/rulemaking/other)
- type: str     (artifact: publication/press_release/rule/guidance/etc.)
- jurisdiction: str
- year: int (preferred) or str (tolerated)
- spider: str
- source_type: str

Filters (input):
- regulators: list[str]
- categories: list[str]
- types: list[str]
- jurisdiction: str
- year: int|str|{"$gte":..,"$lte":..}
- spiders: list[str]
- source_types: list[str]
- sort: "latest" (optional)

Adds:
- "latest" mode: bias candidate pool + final results toward newest by date/year.
"""

import asyncio
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from langchain_cohere import CohereRerank
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from observability.logger import log_error, log_info, log_warning
from .vector_store import get_vector_store

DEFAULT_TOP_K = int(os.getenv("HYBRID_TOP_K", 8))
DEFAULT_BM25_WEIGHT = float(os.getenv("HYBRID_BM25_WEIGHT", 0.4))
DEFAULT_VECTOR_WEIGHT = float(os.getenv("HYBRID_VECTOR_WEIGHT", 0.6))
DEFAULT_CANDIDATE_MULTIPLIER = int(os.getenv("HYBRID_CANDIDATE_MULTIPLIER", 4))

# Candidate pool caps (BM25 is built from store.get() output)
DEFAULT_BM25_POOL_LIMIT = int(os.getenv("HYBRID_BM25_POOL_LIMIT", 800))
DEFAULT_LATEST_POOL = int(os.getenv("HYBRID_LATEST_POOL", 250))

RRF_K = 60

_LATEST_RE = re.compile(
    r"\b(latest|recent|newest|current|most\s+recent|up[-\s]?to[-\s]?date)\b", re.I
)


def _normalize_list(val: Any) -> Optional[List[Any]]:
    if val is None:
        return None
    if isinstance(val, list):
        return val if val else None
    return [val]


def _safe_int(val: Any) -> Optional[int]:
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _build_year_condition(year: Any) -> Optional[Dict[str, Any]]:
    """Match year stored as int OR str. Supports range dict."""
    if year is None:
        return None

    if isinstance(year, dict):
        gte = _safe_int(year.get("$gte"))
        lte = _safe_int(year.get("$lte"))
        if gte is None and lte is None:
            return None

        numeric_range: Dict[str, Any] = {}
        if gte is not None:
            numeric_range["$gte"] = gte
        if lte is not None:
            numeric_range["$lte"] = lte

        # Best-effort string support: expand a reasonable discrete list
        years: List[int] = []
        if gte is not None and lte is not None and lte >= gte:
            years = list(range(gte, lte + 1))
        elif gte is not None:
            years = list(range(gte, gte + 6))
        elif lte is not None:
            years = list(range(max(1900, lte - 5), lte + 1))

        or_parts: List[Dict[str, Any]] = [{"year": numeric_range}]
        if years:
            or_parts.append({"year": {"$in": [str(y) for y in years]}})
        return {"$or": or_parts}

    y_int = _safe_int(year)
    y_str = str(year).strip()
    if y_int is not None:
        return {"$or": [{"year": y_int}, {"year": y_str}]}
    return {"year": y_str} if y_str else None


def _build_where(filters: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Approach A only:
      - regulators -> regulator ($in)
      - categories -> category ($in)
      - types      -> type ($in)
      - jurisdiction -> jurisdiction
      - spiders -> spider ($in)
      - source_types -> source_type ($in)
      - year -> year (int/str tolerant)
    """
    if not filters:
        return None

    conditions: List[Dict[str, Any]] = []

    regs = _normalize_list(filters.get("regulators"))
    if regs:
        conditions.append({"regulator": {"$in": regs}})

    cats = _normalize_list(filters.get("categories"))
    if cats:
        conditions.append({"category": {"$in": cats}})

    types_ = _normalize_list(filters.get("types"))
    if types_:
        conditions.append({"type": {"$in": types_}})

    juris = filters.get("jurisdiction")
    if juris:
        conditions.append({"jurisdiction": juris})

    spiders = _normalize_list(filters.get("spiders"))
    if spiders:
        conditions.append({"spider": {"$in": spiders}})

    source_types = _normalize_list(filters.get("source_types"))
    if source_types:
        conditions.append({"source_type": {"$in": source_types}})

    year_cond = _build_year_condition(filters.get("year"))
    if year_cond:
        conditions.append(year_cond)

    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def _wants_latest(query: str, filters: Optional[Dict[str, Any]]) -> bool:
    if filters and str(filters.get("sort", "")).lower() == "latest":
        return True
    return bool(_LATEST_RE.search(query or ""))


def _parse_date_to_epoch(date_val: Any) -> Optional[float]:
    """
    Returns epoch seconds if parseable, else None.
    IMPORTANT: your pipeline stores date as a *string* (e.g. ISO or 'Unknown')
    """
    if not date_val:
        return None

    s = str(date_val).strip()
    if not s or s.lower() in {"unknown", "n/a", "na", "none"}:
        return None

    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        pass

    for fmt in (
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%m/%d/%Y",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.timestamp()
        except Exception:
            continue

    return None


def _recency_key(doc: Document) -> Tuple[int, int]:
    """
    Primary: parsed date epoch (date/creationdate/moddate)
    Secondary: year int
    """
    md = doc.metadata or {}

    epoch = _parse_date_to_epoch(md.get("date"))
    if epoch is None:
        epoch = _parse_date_to_epoch(md.get("moddate")) or _parse_date_to_epoch(md.get("creationdate"))

    y = _safe_int(md.get("year")) or 0
    return (int(epoch) if epoch is not None else 0, y)


def _doc_identity(doc: Document) -> str:
    """
    Stable ID for fusion/dedup.
    Prefer doc_id, then url. Fallback to a deterministic content prefix.
    """
    md = doc.metadata or {}
    for key in ("doc_id", "url", "id", "document_id", "source"):
        v = md.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return (doc.page_content or "")[:300]


async def apply_rrf(
    vector_results: List[Document],
    bm25_results: List[Document],
    weights: Tuple[float, float],
    limit: int,
) -> List[Document]:
    rrf_score: Dict[str, float] = defaultdict(float)
    doc_map: Dict[str, Document] = {}

    # order aligns with weights: (bm25, vector)
    sources = [(bm25_results, weights[0]), (vector_results, weights[1])]

    for docs, weight in sources:
        for rank, doc in enumerate(docs, start=1):
            doc_id = _doc_identity(doc)
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
    bw = DEFAULT_BM25_WEIGHT if bm25_weight is None else max(0.0, bm25_weight)
    vw = DEFAULT_VECTOR_WEIGHT if vector_weight is None else max(0.0, vector_weight)
    if bw == 0 and vw == 0:
        bw, vw = DEFAULT_BM25_WEIGHT, DEFAULT_VECTOR_WEIGHT

    candidate_k = max(top_k * DEFAULT_CANDIDATE_MULTIPLIER, top_k)
    latest_mode = _wants_latest(query, filters)

    log_info(
        f"🔎 [Hybrid Search] Query: {query[:80]} | Filters: {filters} | latest_mode={latest_mode}"
    )

    try:
        store = get_vector_store()

        where = _build_where(filters)
        if where:
            log_info(f"🎯 Chroma where: {where}")

        # Vector retriever (LangChain expects 'filter')
        search_kwargs: Dict[str, Any] = {"k": candidate_k}
        if where:
            search_kwargs["filter"] = where
        vector_retriever = store.as_retriever(search_kwargs=search_kwargs)

        # BM25 candidate pool (Chroma get expects 'where')
        pool_limit = max(DEFAULT_LATEST_POOL, candidate_k * 8) if latest_mode else DEFAULT_BM25_POOL_LIMIT

        try:
            filtered_data = (
                store.get(where=where, limit=pool_limit, include=["documents", "metadatas"])
                if where
                else store.get(limit=pool_limit, include=["documents", "metadatas"])
            )
        except TypeError:
            # Some wrappers might not accept include/limit; fall back safely
            filtered_data = store.get(where=where) if where else store.get()

        docs_raw = (filtered_data or {}).get("documents") or []
        metas_raw = (filtered_data or {}).get("metadatas") or []

        if not docs_raw:
            log_warning("📭 No docs in BM25 pool. Returning vector-only results.")
            return await vector_retriever.ainvoke(query)

        # Zip defensively
        if len(metas_raw) != len(docs_raw):
            metas_raw = metas_raw + ([{}] * (len(docs_raw) - len(metas_raw)))

        all_docs = [
            Document(page_content=(doc or "").strip(), metadata=(meta or {}))
            for doc, meta in zip(docs_raw, metas_raw)
            if doc and str(doc).strip()
        ]

        if not all_docs:
            log_warning("📭 BM25 pool empty after cleaning. Returning vector-only results.")
            return await vector_retriever.ainvoke(query)

        # Latest-mode: sort candidate pool first to make BM25 reflect “latest”
        if latest_mode:
            all_docs.sort(key=_recency_key, reverse=True)
            all_docs = all_docs[:pool_limit]
            log_info(f"🕒 latest_mode BM25 pool size: {len(all_docs)}")

        bm25_retriever = BM25Retriever.from_documents(documents=all_docs)
        bm25_retriever.k = candidate_k

        bm25_results, vector_results = await asyncio.gather(
            bm25_retriever.ainvoke(query),
            vector_retriever.ainvoke(query),
        )

        fused = await apply_rrf(
            vector_results=vector_results,
            bm25_results=bm25_results,
            weights=(bw, vw),
            limit=candidate_k,
        )

        # Final newest-bias for latest mode (after fusion)
        if latest_mode and fused:
            fused.sort(key=_recency_key, reverse=True)

        # Optional reranking
        cohere_key = os.getenv("COHERE_API_KEY")
        if use_reranker and cohere_key and fused:
            try:
                reranker = CohereRerank(model="rerank-english-v3.0", top_n=top_k)
                reranked = reranker.compress_documents(fused, query)
                if latest_mode and reranked:
                    reranked.sort(key=_recency_key, reverse=True)
                return reranked[:top_k]
            except Exception as e:
                log_error(f"Reranker failed: {e}")
                return fused[:top_k]

        return fused[:top_k]

    except Exception as e:
        log_error(f"❌ Hybrid search failure: {e}", exc_info=True)
        return []