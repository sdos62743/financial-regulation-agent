"""
Interactive Chroma collection cleanup — list collections, delete by name or all.
"""
import chromadb
import os
import sys
from pathlib import Path

# Add project root to path before any project imports
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")
from observability.logger import log_info, log_warning
DEFAULT_DB_PATH = BASE_DIR / "data" / "chroma_db"
PERSIST_PATH = os.getenv("CHROMA_PERSIST_DIR", str(DEFAULT_DB_PATH))

def manage_collections():
    if not os.path.exists(PERSIST_PATH):
        log_warning(f"❌ Path {PERSIST_PATH} not found. Check your vector_store.py settings.")
        return

    # Initialize the Persistent Client
    client = chromadb.PersistentClient(path=PERSIST_PATH)

    # 1. List all collections (Chroma v0.6+ returns names, not Collection objects)
    collection_names = client.list_collections()

    if not collection_names:
        print("📭 No collections found in the database.")
        return

    print("\n--- 📦 Existing Collections ---")
    for i, name in enumerate(collection_names):
        col = client.get_collection(name)
        print(f"{i+1}. Name: {name} (Items: {col.count()})")
    print("-------------------------------\n")

    # 2. Ask which one to delete
    target_name = input("Type the NAME of the collection you want to DELETE (or 'all' to wipe everything): ").strip()

    try:
        if target_name.lower() == 'all':
            for name in collection_names:
                client.delete_collection(name)
                log_info(f"🗑️ Deleted: {name}")
        else:
            client.delete_collection(target_name)
            log_info(f"🗑️ Successfully deleted collection: {target_name}")

        print("✅ Cleanup complete. You are ready to re-ingest.")

    except Exception as e:
        print(f"❌ Error during deletion: {e}")

if __name__ == "__main__":
    manage_collections()
