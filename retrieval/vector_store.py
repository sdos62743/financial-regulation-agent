from __future__ import annotations

"""
Optimized Chroma Vector Store for Regulatory RAG.
Features: Singleton pattern, Batching, and Metadata persistence.
"""

import os
import uuid
from pathlib import Path
from typing import List, TYPE_CHECKING

from dotenv import load_dotenv
from langchain_chroma import Chroma
from observability.logger import log_error, log_info, log_warning
from .embeddings import get_embeddings

if TYPE_CHECKING:
    from langchain_core.documents import Document

# 🔹 IMPROVED: Recursive Project Root Discovery
def _get_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in current.parents:
        if (parent / ".env").exists() or (parent / "data").exists():
            return parent
    return current.parent.parent # Fallback

BASE_DIR = _get_root()

# Load .env from the absolute project root
load_dotenv(BASE_DIR / ".env")

# 🔹 FIX: Ensure PERSIST_DIRECTORY is always absolute relative to BASE_DIR
env_path = os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")
if os.path.isabs(env_path):
    PERSIST_DIRECTORY = env_path
else:
    PERSIST_DIRECTORY = str((BASE_DIR / env_path).resolve())

COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "financial_regulation")

_vector_store: Chroma | None = None

def get_vector_store() -> Chroma:
    """Returns the Chroma singleton. Configured with Cosine Similarity."""
    global _vector_store

    if _vector_store is None:
        try:
            # Ensure the directory exists physically
            os.makedirs(PERSIST_DIRECTORY, exist_ok=True)
            
            log_info(f"Initializing Chroma | Collection: {COLLECTION_NAME}")
            log_info(f"📍 Absolute Path: {PERSIST_DIRECTORY}")

            embeddings = get_embeddings()

            _vector_store = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=embeddings,
                persist_directory=PERSIST_DIRECTORY,
                collection_metadata={"hnsw:space": "cosine"}
            )
            
            # Diagnostic check on init
            count = _vector_store._collection.count()
            log_info(f"✅ Chroma initialized. Records in collection: {count}")
            
        except Exception as e:
            log_error(f"Vector Store Init Failed: {e}")
            raise RuntimeError("DB Initialization Error") from e

    return _vector_store

def add_documents(docs: List[Document], batch_size: int = 500) -> None:
    """Adds documents in batches with unique IDs."""
    if not docs:
        log_warning("No documents to add.")
        return

    store = get_vector_store()
    
    # Ensure IDs exist for upsert/deduplication logic
    for doc in docs:
        if "id" not in doc.metadata:
            doc.metadata["id"] = str(uuid.uuid4())

    try:
        for i in range(0, len(docs), batch_size):
            batch = docs[i : i + batch_size]
            store.add_documents(batch)
            log_info(f"Added batch {i//batch_size + 1}: {len(batch)} chunks")
            
        log_info(f"✅ Successfully ingested total {len(docs)} chunks")
    except Exception as e:
        log_error(f"Ingestion failed: {e}")
        raise

def clear_collection() -> None:
    """Wipes the DB collection."""
    global _vector_store
    try:
        store = get_vector_store()
        store.delete_collection()
        _vector_store = None
        log_warning(f"🗑️ Collection '{COLLECTION_NAME}' deleted.")
    except Exception as e:
        log_error(f"Clear failed: {e}")
        raise

def get_collection_count() -> int:
    """Returns total vector count."""
    try:
        store = get_vector_store()
        return store._collection.count()
    except Exception as e:
        log_error(f"Count failed: {e}")
        return 0