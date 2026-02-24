"""
Chroma health check: total count, peek last 5 metadata entries, similarity search test.
"""

import os
import sys
from pathlib import Path

# Add project root to path before any project imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")
import chromadb

from retrieval.vector_store import get_vector_store


def diagnostic():
    # 1. Check total count
    persist_path = os.getenv("CHROMA_PERSIST_DIR", str(BASE_DIR / "data" / "chroma_db"))
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "financial_regulation")

    client = chromadb.PersistentClient(path=persist_path)
    collection = client.get_collection(name=collection_name)

    count = collection.count()
    print(f"📊 Total documents in Chroma: {count}")

    # 2. Peek at the most recent entries
    if count > 0:
        last_docs = collection.peek(limit=5)
        print("\n👀 Last 5 Metadata entries:")
        for meta in last_docs["metadatas"]:
            print(f" - {meta}")

    # 3. Test a direct retrieval (bypass the graph)
    print("\n🧪 Testing direct similarity search for 'Basel'...")
    vs = get_vector_store()
    results = vs.similarity_search("What is Basel?", k=2)
    print(f" ✅ Found {len(results)} results via similarity search.")


if __name__ == "__main__":
    diagnostic()
