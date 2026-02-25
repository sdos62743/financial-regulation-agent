#!/usr/bin/env python3
"""
Production-ready Ingestion Pipeline (Approach A ONLY)

Loads scraped JSON files → chunks → embeds → stores in Chroma.

Approach A schema written into Chroma metadata (STRICT):
- regulator: str
- category: str (semantic: policy/enforcement/rulemaking/guidance/litigation/supervisory/compliance/other)
- type: str     (artifact: press_release/publication/speech/rule/guidance/etc.)
- jurisdiction: str
- year: int
- date: str (NEVER None; "Unknown" if missing)
- spider: str
- source_type: str ("web_page" | "document")
- doc_id: str
- url: str
- title: str
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# === CRITICAL: Add project root to PYTHONPATH ===
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before any imports that need API keys
from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from langchain_core.documents import Document  # noqa: E402

from observability.logger import log_error, log_info, log_warning  # noqa: E402
from retrieval.chunking import get_text_splitter  # noqa: E402
from retrieval.vector_store import add_documents, clear_collection, get_collection_count  # noqa: E402


_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


# ----------------------------
# Helpers (Chroma-safe)
# ----------------------------
def _safe_int(val: Any) -> Optional[int]:
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _clean_date(date_val: Any) -> str:
    """
    Chroma-safe: must always be a string (no None).
    Prefer keeping original string; do not invent real dates.
    """
    if not date_val:
        return "Unknown"
    s = str(date_val).strip()
    return s if s else "Unknown"


def _infer_year(item: Dict[str, Any], date_str: str) -> int:
    """
    Prefer explicit item['year'] (int-like) else parse year from date string else current year.
    """
    y = _safe_int(item.get("year"))
    if y:
        return y

    m = _YEAR_RE.search(date_str or "")
    if m:
        y2 = _safe_int(m.group(1))
        if y2:
            return y2

    return datetime.utcnow().year


def _clean_scalar_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chroma requires metadata values to be str/int/float/bool.
    Also: no None anywhere.
    """
    out: Dict[str, Any] = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[k] = v
        else:
            out[k] = str(v)

    # final guard
    return {k: ("N/A" if v is None else v) for k, v in out.items()}


def _derive_source_type(item: Dict[str, Any]) -> str:
    # Prefer explicit item source_type if your spiders set it; else infer.
    st = item.get("source_type")
    if isinstance(st, str) and st.strip():
        return st.strip()
    return "document" if item.get("files") or item.get("file_urls") else "web_page"


def _derive_artifact_type(item: Dict[str, Any], source_type: str) -> str:
    # Approach A: type = artifact kind (press_release/publication/speech/...)
    t = item.get("type")
    if isinstance(t, str) and t.strip():
        return t.strip()
    return "document" if source_type == "document" else "web_page"


def _derive_category(item: Dict[str, Any]) -> str:
    c = item.get("category")
    if isinstance(c, str) and c.strip():
        return c.strip()
    return "other"


def _derive_spider(item: Dict[str, Any]) -> str:
    s = item.get("spider") or item.get("spider_name")
    if isinstance(s, str) and s.strip():
        return s.strip()
    return "unknown_spider"


def _derive_doc_id(item: Dict[str, Any]) -> str:
    d = item.get("doc_id")
    if d is None:
        return "unknown_id"
    s = str(d).strip()
    return s if s else "unknown_id"


# ----------------------------
# Load + Convert
# ----------------------------
def load_scraped_files(scraped_dir: Path) -> List[Path]:
    """Load all JSON files from scraped directory"""
    if not scraped_dir.exists():
        log_error(f"Directory not found: {scraped_dir}")
        return []

    files = sorted(scraped_dir.glob("*.json"))
    log_info(f"Found {len(files)} scraped JSON files in {scraped_dir}")
    return files


def json_to_documents(json_path: Path) -> List[Document]:
    """Convert a scraped JSON file into LangChain Documents (Approach A strict)."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = [data]

        documents: List[Document] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            content = (item.get("content") or "").strip()
            if not content:
                continue

            # Approach A fields
            regulator = (item.get("regulator") or "Unknown").strip() if isinstance(item.get("regulator"), str) else (item.get("regulator") or "Unknown")
            jurisdiction = (item.get("jurisdiction") or "Global").strip() if isinstance(item.get("jurisdiction"), str) else (item.get("jurisdiction") or "Global")

            source_type = _derive_source_type(item)
            artifact_type = _derive_artifact_type(item, source_type)
            category = _derive_category(item)
            spider = _derive_spider(item)
            doc_id = _derive_doc_id(item)

            raw_date = item.get("date") or item.get("publication_date")
            clean_date = _clean_date(raw_date)
            clean_year = _infer_year(item, clean_date)

            title = item.get("title")
            if not isinstance(title, str) or not title.strip():
                title = doc_id

            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                url = "https://unknown.regulator.gov"

            meta = {
                "url": url.strip(),
                "date": clean_date,  # ✅ string only
                "year": clean_year,  # ✅ int
                "title": title.strip(),
                "regulator": regulator,
                "jurisdiction": jurisdiction,

                # ✅ Approach A
                "type": artifact_type,
                "category": category,
                "source_type": source_type,
                "spider": spider,

                "doc_id": doc_id,
                "ingest_timestamp": item.get("ingest_timestamp") or datetime.utcnow().isoformat(),
                "source_file": json_path.name,
            }

            meta = _clean_scalar_metadata(meta)
            documents.append(Document(page_content=content, metadata=meta))

        return documents

    except Exception as e:
        log_error(f"Failed to parse {json_path.name}: {e}")
        return []


# ----------------------------
# Main
# ----------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Financial Regulation Ingestion Pipeline (Approach A)")
    parser.add_argument("--limit", type=int, default=None, help="Max chunks to ingest total")
    parser.add_argument("--clear", action="store_true", help="Clear vector DB before ingesting")
    parser.add_argument("--mock", action="store_true", help="Use mock data folder instead of scraped")
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size for vector DB insertion")
    parser.add_argument("--chunk-size", type=int, default=1100, help="Chunk size")
    parser.add_argument("--chunk-overlap", type=int, default=180, help="Chunk overlap")
    args = parser.parse_args()

    # 1) Database maintenance
    if args.clear:
        log_warning("Cleaning up vector database...")
        clear_collection()

    # 2) Path setup
    data_dir = PROJECT_ROOT / ("data/mock" if args.mock else "data/scraped")
    json_files = load_scraped_files(data_dir)
    if not json_files:
        log_warning(f"No JSON files found in {data_dir}")
        return

    # 3) Chunking config
    splitter = get_text_splitter(method="recursive", chunk_size=args.chunk_size, chunk_overlap=args.chunk_overlap)

    total_chunks_processed = 0

    # 4) Process each JSON file
    for json_file in json_files:
        docs = json_to_documents(json_file)
        if not docs:
            continue

        chunks = splitter.split_documents(docs)
        if not chunks:
            continue

        # optional global limit
        if args.limit is not None and total_chunks_processed + len(chunks) > args.limit:
            chunks = chunks[: max(0, args.limit - total_chunks_processed)]

        if not chunks:
            break

        log_info(f"Ingesting {len(chunks)} chunks from {json_file.name}...")

        # 5) Batch insert
        for i in range(0, len(chunks), args.batch_size):
            batch = chunks[i : i + args.batch_size]
            try:
                add_documents(batch)
            except Exception as e:
                log_error(f"Batch insertion failed for {json_file.name} [{i}:{i + len(batch)}]: {e}")
                continue

        total_chunks_processed += len(chunks)
        if args.limit is not None and total_chunks_processed >= args.limit:
            break

    log_info(f"✅ Ingestion completed. Total chunks in DB: {get_collection_count()}")


if __name__ == "__main__":
    main()