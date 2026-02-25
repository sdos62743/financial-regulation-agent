#!/usr/bin/env python3
"""
scripts/diagnose_chroma.py

Inspect Chroma documents + verify Approach A schema consistency.

Compatible with Chroma include() behavior that does NOT accept "ids" in include list.

Usage:
  python3.11 scripts/diagnose_chroma.py
  python3.11 scripts/diagnose_chroma.py --limit 50
  python3.11 scripts/diagnose_chroma.py --regulator BASEL
  python3.11 scripts/diagnose_chroma.py --regulator BASEL --category policy
  python3.11 scripts/diagnose_chroma.py --regulator CFTC --type press_release --year 2026

Env:
  CHROMA_PERSIST_DIR (default: data/chroma_db)
  CHROMA_COLLECTION_NAME (default: financial_regulation)
"""

import argparse
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Optional

import chromadb
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _resolve_chroma() -> tuple[str, str]:
    rel_path = os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")
    abs_path = str((BASE_DIR / rel_path).resolve())
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "financial_regulation")
    return abs_path, collection_name


def _normalize_year_condition(year: str) -> Dict[str, Any]:
    """
    Match year stored as int OR str.
    """
    try:
        y = int(year)
        return {"$or": [{"year": y}, {"year": str(y)}]}
    except (ValueError, TypeError):
        return {"year": str(year)}


def _build_where(
    regulator: Optional[str],
    category: Optional[str],
    type_: Optional[str],
    year: Optional[str],
) -> Optional[Dict[str, Any]]:
    conditions = []

    if regulator:
        conditions.append({"regulator": regulator})
    if category:
        conditions.append({"category": category})
    if type_:
        conditions.append({"type": type_})
    if year:
        conditions.append(_normalize_year_condition(year))

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _print_meta(meta: Dict[str, Any]) -> None:
    print("\n--- 🔍 METADATA SAMPLE ---")
    for key in sorted(meta.keys()):
        v = meta.get(key)
        print(f"{key}: {v!r} ({type(v).__name__})")


def _schema_checks(meta: Dict[str, Any]) -> None:
    print("\n--- ✅ SCHEMA CHECKS (Approach A) ---")

    y = meta.get("year")
    if isinstance(y, int):
        print("✨ year: OK (int)")
    elif y is None:
        print("⚠️ year: MISSING")
    else:
        print(f"⚠️ year: NOT int (got {type(y).__name__}: {y!r})")

    t = meta.get("type")
    c = meta.get("category")

    if t is None:
        print("⚠️ type: MISSING (artifact kind like press_release/rule/publication)")
    else:
        print(f"✨ type: present ({t!r})")

    if c is None:
        print(
            "⚠️ category: MISSING (semantic like enforcement/policy/rulemaking/other)"
        )
    else:
        print(f"✨ category: present ({c!r})")

    for k in (
        "regulator",
        "jurisdiction",
        "source_type",
        "spider",
        "doc_id",
        "url",
        "title",
        "date",
    ):
        if meta.get(k) is None:
            print(f"⚠️ {k}: MISSING")

    print("✅ Done.")


def diagnose(
    limit: int,
    regulator: str | None,
    category: str | None,
    type_: str | None,
    year: str | None,
) -> None:
    abs_path, collection_name = _resolve_chroma()

    print(f"📂 Path: {abs_path}")
    print(f"📦 Collection: {collection_name}")

    if not os.path.exists(abs_path):
        print("❌ ERROR: CHROMA_PERSIST_DIR path not found.")
        return

    client = chromadb.PersistentClient(path=abs_path)

    try:
        col = client.get_collection(name=collection_name)
    except Exception as e:
        print(f"❌ ERROR: Could not access collection '{collection_name}'.")
        print(f"Details: {e}")
        return

    try:
        count = col.count()
        print(f"✅ SUCCESS! Found {count} documents.")
    except Exception as e:
        print(f"❌ ERROR: Could not count docs. Details: {e}")
        return

    if count <= 0:
        print("📭 Collection is empty.")
        return

    where = _build_where(regulator, category, type_, year)
    if where:
        print(f"\n🎯 WHERE filter: {where}")

    try:
        # IMPORTANT: do NOT include "ids" in include list (Chroma rejects it).
        include = ["metadatas", "documents"]
        if where:
            sample = col.get(where=where, limit=min(limit, 500), include=include)
        else:
            sample = col.get(limit=min(limit, 500), include=include)
    except Exception as e:
        print(f"❌ ERROR: Could not fetch sample docs. Details: {e}")
        return

    metadatas = sample.get("metadatas") or []
    documents = sample.get("documents") or []
    ids = sample.get("ids") or []  # Chroma returns ids automatically

    if not metadatas:
        print("📭 No documents returned for this filter/sample.")
        return

    meta0 = metadatas[0] or {}
    _print_meta(meta0)
    _schema_checks(meta0)

    doc0 = documents[0] if documents else ""
    if doc0:
        print("\n--- 🧾 CONTENT PREVIEW ---")
        print(doc0[:500].replace("\n", "\\n"))

    print(f"\n--- 📊 DISTRIBUTIONS (from {len(metadatas)} sampled docs) ---")
    reg_ctr = Counter()
    type_ctr = Counter()
    cat_ctr = Counter()
    year_types = Counter()

    for md in metadatas:
        md = md or {}
        reg_ctr[md.get("regulator")] += 1
        type_ctr[md.get("type")] += 1
        cat_ctr[md.get("category")] += 1
        year_types[type(md.get("year")).__name__] += 1

    def _print_top(name: str, ctr: Counter, topn: int = 10) -> None:
        print(f"\n{name}:")
        for k, v in ctr.most_common(topn):
            print(f"  {k!r}: {v}")

    _print_top("By regulator", reg_ctr)
    _print_top("By type (artifact)", type_ctr)
    _print_top("By category (semantic)", cat_ctr)
    _print_top("Year value types", year_types)

    print("\n--- 🔗 SAMPLE IDS/URLS ---")
    for i in range(min(8, len(metadatas))):
        md = metadatas[i] or {}
        print(
            f"- id={ids[i] if i < len(ids) else 'N/A'}"
            f" | regulator={md.get('regulator')}"
            f" | category={md.get('category')}"
            f" | type={md.get('type')}"
            f" | year={md.get('year')}"
            f" | url={md.get('url')}"
        )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--limit", type=int, default=25, help="How many docs to sample (max 500)."
    )
    p.add_argument(
        "--regulator",
        type=str,
        default=None,
        help='Filter by regulator code (e.g., "BASEL").',
    )
    p.add_argument(
        "--category",
        type=str,
        default=None,
        help='Filter by semantic category (e.g., "policy").',
    )
    p.add_argument(
        "--type",
        dest="type_",
        type=str,
        default=None,
        help='Filter by artifact type (e.g., "press_release", "publication").',
    )
    p.add_argument(
        "--year",
        type=str,
        default=None,
        help='Filter by year (e.g., "2026"). Matches int or str stored values.',
    )
    args = p.parse_args()

    diagnose(
        limit=args.limit,
        regulator=args.regulator,
        category=args.category,
        type_=args.type_,
        year=args.year,
    )


if __name__ == "__main__":
    main()
