#!/usr/bin/env python3
"""
Production-ready Ingestion Pipeline
Loads scraped JSON files → chunks → embeds → stores in Chroma.
"""

import sys
import os
from pathlib import Path

# === CRITICAL: Add project root to PYTHONPATH ===
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import json
import argparse
from datetime import datetime
from typing import List

from langchain_core.documents import Document
from retrieval.chunking import get_text_splitter
from retrieval.vector_store import add_documents, clear_collection, get_collection_count
from observability.logger import log_error, log_info, log_warning

def load_scraped_files(scraped_dir: Path):
    """Load all JSON files from scraped directory"""
    if not scraped_dir.exists():
        log_error(f"Directory not found: {scraped_dir}")
        return []

    files = list(scraped_dir.glob("*.json"))
    log_info(f"Found {len(files)} scraped JSON files")
    return sorted(files)

def json_to_documents(json_path: Path) -> List[Document]:
    """Convert scraped JSON into LangChain Documents"""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = [data]

        documents = []
        for item in data:
            content = (item.get("content") or "").strip()
            if not content:
                continue

            metadata = {
                "url": item.get("url"),
                "date": item.get("date") or item.get("publication_date"),
                "title": item.get("title"),
                "type": item.get("type") or item.get("source_type"),
                "regulator": item.get("regulator"),
                "jurisdiction": item.get("jurisdiction"),
                "doc_id": str(item.get("doc_id") or ""),
                "speaker": item.get("speaker"),
                "spider_name": item.get("spider_name"),
                "ingest_timestamp": item.get("ingest_timestamp") or datetime.utcnow().isoformat(),
                "source_file": json_path.name,
            }
            metadata = {k: v for k, v in metadata.items() if v is not None}
            documents.append(Document(page_content=content, metadata=metadata))

        return documents

    except Exception as e:
        log_error(f"Failed to parse {json_path.name}: {e}")
        return []

def main():
    parser = argparse.ArgumentParser(description="Financial Regulation Ingestion Pipeline")
    parser.add_argument("--limit", type=int, default=None, help="Max documents to ingest")
    parser.add_argument("--clear", action="store_true", help="Clear vector DB before ingesting")
    parser.add_argument("--mock", action="store_true", help="Use mock data")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size for vector DB insertion")
    args = parser.parse_args()

    # 1. Database Maintenance
    if args.clear:
        log_warning("Cleaning up vector database...")
        clear_collection()

    # 2. Path Setup
    data_dir = PROJECT_ROOT / ("data/mock" if args.mock else "data/scraped")
    json_files = load_scraped_files(data_dir)

    if not json_files:
        log_warning(f"No JSON files found in {data_dir}")
        return

    # 3. Chunking Configuration
    splitter = get_text_splitter(method="recursive", chunk_size=1100, chunk_overlap=180)

    total_chunks_processed = 0

    # 4. Processing Loop
    for json_file in json_files:
        docs = json_to_documents(json_file)
        if not docs:
            continue
            
        chunks = splitter.split_documents(docs)
        
        if args.limit and total_chunks_processed + len(chunks) > args.limit:
            chunks = chunks[:args.limit - total_chunks_processed]

        if not chunks:
            continue

        log_info(f"Ingesting {len(chunks)} chunks from {json_file.name}...")
        for i in range(0, len(chunks), args.batch_size):
            batch = chunks[i : i + args.batch_size]
            try:
                add_documents(batch)
            except Exception as e:
                log_error(f"Batch insertion failed: {e}")
                continue

        total_chunks_processed += len(chunks)
        if args.limit and total_chunks_processed >= args.limit:
            break

    log_info(f"✅ Ingestion completed. Total chunks in DB: {get_collection_count()}")

if __name__ == "__main__":
    main()