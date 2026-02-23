from __future__ import annotations

"""
Optimized Chroma Vector Store for Regulatory RAG.
Features: Singleton pattern, Batching, and Metadata persistence.
"""

import os
from typing import List, TYPE_CHECKING
import uuid

from langchain_chroma import Chroma
from observability.logger import log_error, log_info, log_warning
from .embeddings import get_embeddings

if TYPE_CHECKING:
    from langchain_core.documents import Document

# Configuration
PERSIST_DIRECTORY = os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")
COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "financial_regulation")

_vector_store: Chroma | None = None

def get_vector_store() -> Chroma:
    """Returns the Chroma singleton. Configured with Cosine Similarity."""
    global _vector_store

    if _vector_store is None:
        try:
            log_info(f"Initializing Chroma | Collection: {COLLECTION_NAME}")
            os.makedirs(PERSIST_DIRECTORY, exist_ok=True)

            embeddings = get_embeddings()

            _vector_store = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=embeddings,
                persist_directory=PERSIST_DIRECTORY,
                collection_metadata={"hnsw:space": "cosine"}
            )
            log_info("✅ Chroma vector store initialized")
        except Exception as e:
            log_error(f"Vector Store Init Failed: {e}")
            raise RuntimeError("DB Initialization Error") from e

    return _vector_store

def add_documents(docs: List[Document], batch_size: int = 500) -> None:
    """
    Adds documents in batches.
    Batching prevents 'too many open files' or memory issues with large SEC filings.
    """
    if not docs:
        log_warning("No documents to add.")
        return

    store = get_vector_store()
    
    # Ensure every doc has a unique ID to prevent duplicates if crawler restarts
    for doc in docs:
        if "id" not in doc.metadata:
            doc.metadata["id"] = str(uuid.uuid4())

    try:
        # Batch processing for stability
        for i in range(0, len(docs), batch_size):
            batch = docs[i : i + batch_size]
            store.add_documents(batch)
            log_info(f"Added batch {i//batch_size + 1}: {len(batch)} chunks")
            
        log_info(f"✅ Successfully ingested total {len(docs)} chunks")
    except Exception as e:
        log_error(f"Ingestion failed: {e}")
        raise

def clear_collection() -> None:
    """Wipes the DB collection - use with caution."""
    global _vector_store
    try:
        store = get_vector_store()
        # Newer Chroma versions use delete_collection()
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
        # Using the standard count method
        return store._collection.count()
    except Exception as e:
        log_error(f"Count failed: {e}")
        return 0