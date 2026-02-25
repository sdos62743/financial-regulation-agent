# graph/nodes/extract_filters.py

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

from app.llm_config import get_llm
from graph.prompts.loader import load_prompt
from graph.state import AgentState
from observability.logger import log_error, log_info, log_warning
from observability.metrics import record_token_usage

# ----------------------------
# Config / constants
# ----------------------------
SUPPORTED_REGULATORS = {"BASEL", "SEC", "CFTC", "FED", "FINCEN", "FCA", "FDIC"}

LATEST_RE = re.compile(
    r"\b(latest|recent|newest|current|most\s+recent|up[-\s]?to[-\s]?date)\b", re.I
)

# Map real-world mentions to your regulator codes
REGULATOR_SYNONYMS = {
    "BASEL": [
        "BASEL",
        "BCBS",
        "BASEL COMMITTEE",
        "BASEL COMMITTEE ON BANKING SUPERVISION",
    ],
    "FED": [
        "FED",
        "FEDERAL RESERVE",
        "BOARD OF GOVERNORS",
        "FOMC",
        "FEDERAL OPEN MARKET COMMITTEE",
    ],
    "SEC": ["SEC", "SECURITIES AND EXCHANGE COMMISSION"],
    "CFTC": ["CFTC", "COMMODITY FUTURES TRADING COMMISSION"],
    "FCA": ["FCA", "FINANCIAL CONDUCT AUTHORITY"],
    "FDIC": ["FDIC", "FEDERAL DEPOSIT INSURANCE CORPORATION"],
    "FINCEN": ["FINCEN", "FINANCIAL CRIMES ENFORCEMENT NETWORK"],
}


# ----------------------------
# Helpers
# ----------------------------
def _normalize_list(v: Any) -> Optional[List[str]]:
    if v is None:
        return None
    if isinstance(v, list):
        out = [str(x).strip() for x in v if x is not None and str(x).strip()]
        return out or None
    s = str(v).strip()
    return [s] if s else None


def _safe_int(v: Any) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        return None


def _extract_regulators_heuristic(query: str) -> Optional[List[str]]:
    q = (query or "").upper()
    found: List[str] = []

    for code, syns in REGULATOR_SYNONYMS.items():
        for s in syns:
            if s.upper() in q:
                found.append(code)
                break

    # allow direct codes too
    for code in SUPPORTED_REGULATORS:
        if code in q and code not in found:
            found.append(code)

    # enforce supported set only
    found = [r for r in found if r in SUPPORTED_REGULATORS]
    return found or None


def _extract_year_heuristic(query: str) -> Optional[int]:
    m = re.search(r"\b(19\d{2}|20\d{2})\b", query or "")
    return int(m.group(1)) if m else None


def _infer_jurisdiction(regs: Optional[List[str]]) -> Optional[str]:
    if not regs:
        return None
    if any(r in regs for r in ["FED", "SEC", "CFTC", "FDIC", "FINCEN"]):
        return "US"
    if "FCA" in regs:
        return "UK"
    if "BASEL" in regs:
        return "Global"
    return None


def _heuristic_filters(query: str) -> Dict[str, Any]:
    regs = _extract_regulators_heuristic(query)
    sort = "latest" if LATEST_RE.search(query or "") else None

    year = _extract_year_heuristic(query)
    if sort:
        year = None  # force year null if "latest/recent"

    jurisdiction = _infer_jurisdiction(regs)

    return {
        "regulators": regs,
        "categories": None,
        "types": None,
        "year": year,
        "jurisdiction": jurisdiction,
        "spiders": None,
        "source_types": None,
        "sort": sort,
    }


def _parse_llm_json(text: str) -> Optional[Dict[str, Any]]:
    t = (text or "").strip()
    if not t:
        return None

    # Remove fenced blocks ```json ... ```
    if "```" in t:
        parts = t.split("```")
        # If it looks like fenced markdown, take the first fenced payload
        if len(parts) >= 3:
            t = parts[1].strip()
            if t.lower().startswith("json"):
                t = t[4:].strip()

    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _normalize_filters(query: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize LLM output into EXACT schema expected by retrieval.hybrid_search:
    regulators, categories, types, year, jurisdiction, spiders, source_types, sort
    """
    base = _heuristic_filters(query)

    regulators = (
        _normalize_list(raw.get("regulators") or raw.get("regulator"))
        or base["regulators"]
    )
    categories = (
        _normalize_list(raw.get("categories") or raw.get("category"))
        or base["categories"]
    )

    # hybrid_search expects "types" (artifact types)
    types_ = (
        _normalize_list(raw.get("types") or raw.get("doc_types") or raw.get("type"))
        or base["types"]
    )

    year_int = (
        _safe_int(raw.get("year")) if raw.get("year") is not None else base["year"]
    )

    jurisdiction = (raw.get("jurisdiction") or "").strip() or base["jurisdiction"]
    spiders = (
        _normalize_list(raw.get("spiders") or raw.get("spider")) or base["spiders"]
    )
    source_types = (
        _normalize_list(raw.get("source_types") or raw.get("source_type"))
        or base["source_types"]
    )

    sort = (raw.get("sort") or "").strip() or base["sort"]

    # If user asked for latest/recent, force latest-mode and year=None
    if LATEST_RE.search(query or ""):
        sort = "latest"
        year_int = None

    # Force: FOMC mentions always imply FED + US + latest unless user specified otherwise
    if re.search(r"\bFOMC\b|Federal Open Market Committee", query or "", re.I):
        if not regulators:
            regulators = ["FED"]
        elif "FED" not in regulators:
            regulators = ["FED"]  # be strict: make it FED-only for this keyword
        jurisdiction = jurisdiction or "US"
        sort = sort or "latest"
        year_int = None if sort == "latest" else year_int

    # Final cleanup: only allow supported regulator codes
    if regulators:
        regulators = [r for r in regulators if r in SUPPORTED_REGULATORS] or None

    # Normalize empty strings to None
    if isinstance(jurisdiction, str) and not jurisdiction.strip():
        jurisdiction = None
    if isinstance(sort, str) and not sort.strip():
        sort = None

    return {
        "regulators": regulators,
        "categories": categories,
        "types": types_,
        "year": year_int,
        "jurisdiction": jurisdiction,
        "spiders": spiders,
        "source_types": source_types,
        "sort": sort,
    }


async def extract_filters(state: AgentState) -> Dict[str, Any]:
    query = (state.get("query") or "").strip()
    log_info(f"🔍 [Extract Filters] Analyzing: {query[:60]}...")

    if not query:
        return {"filters": _heuristic_filters("")}

    try:
        llm = get_llm()
        prompt = load_prompt("extract_filters")
        chain = prompt | llm

        resp = await chain.ainvoke({"query": query})
        raw_text = getattr(resp, "content", "") or ""
        raw_json = _parse_llm_json(raw_text)

        if raw_json is None:
            log_warning("extract_filters: LLM JSON parse failed. Using heuristics.")
            cleaned = _heuristic_filters(query)
        else:
            cleaned = _normalize_filters(query, raw_json)

        asyncio.create_task(_log_filter_metrics(llm, resp))
        return {"filters": cleaned}

    except Exception as e:
        log_error(f"❌ Filter Extraction Error: {e}", exc_info=True)
        return {"filters": _heuristic_filters(query)}


async def _log_filter_metrics(llm, response):
    try:
        model_name = getattr(llm, "model", getattr(llm, "model_name", "unknown"))
        metadata = getattr(response, "response_metadata", {}) or {}
        usage = metadata.get("usage_metadata") or {}
        record_token_usage(model_name, "extract_filters", usage.get("total_tokens", 0))
    except Exception:
        pass
