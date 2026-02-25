"""
Improved CFTC Diagnostic - Shows better metadata and sample content
"""

import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def diagnose_cftc():
    rel_path = os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")
    abs_path = str((BASE_DIR / rel_path).resolve())
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "financial_regulation")

    print(f"📂 Chroma Path : {abs_path}")
    print(f"📦 Collection  : {collection_name}\n")

    client = chromadb.PersistentClient(path=abs_path)
    col = client.get_collection(name=collection_name)

    cftc_docs = col.get(where={"regulator": "CFTC"}, limit=10)

    total_cftc = len(cftc_docs.get("ids", []))
    total_docs = col.count()

    print(f"✅ Total documents in vector store : {total_docs}")
    print(f"✅ CFTC documents found            : {total_cftc}\n")

    if total_cftc > 0:
        print("--- 🔍 SAMPLE CFTC DOCUMENTS (Latest 10) ---")
        for i in range(total_cftc):
            meta = cftc_docs["metadatas"][i]
            print(f"Document {i+1}:")
            print(f"   Title : {meta.get('title', 'N/A')[:100]}")
            print(f"   Date  : {meta.get('date', 'N/A')}")
            print(f"   Year  : {meta.get('year', 'N/A')}")
            print(f"   URL   : {meta.get('url', 'N/A')[:100]}")
            print("-" * 80)


if __name__ == "__main__":
    diagnose_cftc()
