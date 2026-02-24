"""
Inspect sample document metadata in Chroma (for debugging ingestion).
"""

import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv

# Project root (scripts/ is one level below)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def diagnose():
    # Path Resolution
    rel_path = os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")
    abs_path = str((BASE_DIR / rel_path).resolve())
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "financial_regulation")

    print(f"📂 Path: {abs_path}")
    print(f"📦 Collection: {collection_name}")

    if not os.path.exists(abs_path):
        print(f"❌ ERROR: Path not found.")
        return

    # Initialize Client
    client = chromadb.PersistentClient(path=abs_path)

    try:
        col = client.get_collection(name=collection_name)

        count = col.count()
        print(f"✅ SUCCESS! Found {count} documents.")

        if count > 0:
            sample = col.peek(limit=1)
            metadata = sample["metadatas"][0]

            print("\n--- 🔍 METADATA VERIFICATION ---")
            for key, value in metadata.items():
                print(f"{key}: {value} ({type(value).__name__})")

            # Validate the Integer Year for Hybrid Search
            if "year" in metadata and isinstance(metadata["year"], int):
                print("\n✨ SUCCESS: 'year' is correctly stored as an INTEGER.")
            else:
                print(
                    f"\n⚠️ WARNING: 'year' type is {type(metadata.get('year'))}. Should be int."
                )

    except Exception as e:
        print(f"❌ ERROR: Could not access collection '{collection_name}'.")
        print(f"Details: {e}")


if __name__ == "__main__":
    diagnose()
