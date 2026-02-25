from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import List

# 🔹 SILENCE CHROMA TELEMETRY ERRORS (optional; keep if you want)
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.vectorstores.utils import filter_complex_metadata
from langchain_core.documents import Document

from observability.logger import log_error, log_info, log_warning

from .embeddings import get_embeddings


def _get_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in current.parents:
        if (parent / ".env").exists() or (parent / "data").exists():
            return parent
    return current.parent.parent


BASE_DIR = _get_root()
load_dotenv(BASE_DIR / ".env")

env_path = os.getenv("CHROMA_PERSIST_DIR", "data/chroma_db")
if os.path.isabs(env_path):
    PERSIST_DIRECTORY = str(Path(env_path).resolve())
else:
    PERSIST_DIRECTORY = str((BASE_DIR / env_path).resolve())

COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "financial_regulation")

_vector_store: Chroma | None = None


def get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        try:
            os.makedirs(PERSIST_DIRECTORY, exist_ok=True)
            log_info(f"Initializing Chroma | Collection: {COLLECTION_NAME}")

            embeddings = get_embeddings()
            _vector_store = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=embeddings,
                persist_directory=PERSIST_DIRECTORY,
                collection_metadata={"hnsw:space": "cosine"},
            )
            count = _vector_store._collection.count()
            log_info(f"✅ Chroma initialized. Records in collection: {count}")
        except Exception as e:
            log_error(f"Vector Store Init Failed: {e}")
            raise RuntimeError("DB Initialization Error") from e
    return _vector_store


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _stable_chunk_id(doc: Document) -> str:
    """
    Stable, per-CHUNK ID.

    Old behavior used url/doc_id (and maybe page), which COLLIDES across chunks.
    New behavior incorporates a content hash so each chunk from the same document
    gets a unique ID, while remaining stable across re-ingestion.
    """
    md = doc.metadata or {}

    url = (md.get("url") or md.get("source") or "").strip()
    doc_id = (md.get("doc_id") or "").strip()
    page = md.get("page")

    # content hash makes ID unique per chunk
    text = (doc.page_content or "").strip()
    content_hash = _sha1(text[:5000]) if text else "no_content"

    base = f"url={url}::doc_id={doc_id}::page={page}::ch={content_hash}"
    return _sha1(base)


def _sanitize_docs(docs: List[Document]) -> List[Document]:
    """
    - Drops complex metadata types (lists/dicts/datetime/etc.)
    - Replaces None metadata values with 'N/A'
    - Ensures all metadata values are primitive types Chroma accepts
    """
    if not docs:
        return []

    # Removes nested metadata types
    docs = filter_complex_metadata(docs)

    cleaned: List[Document] = []
    for d in docs:
        md = d.metadata or {}

        safe_md = {}
        for k, v in md.items():
            if v is None:
                safe_md[k] = "N/A"
            elif isinstance(v, (str, int, float, bool)):
                safe_md[k] = v
            else:
                safe_md[k] = str(v)

        d.metadata = safe_md
        cleaned.append(d)

    return cleaned


def add_documents(docs: List[Document], batch_size: int = 500) -> None:
    """
    Adds documents in batches with metadata sanitization + stable per-chunk IDs.

    Guarantees:
    - No duplicate IDs within a batch (assert + salt fallback)
    - Stable IDs across runs for the same chunk content
    """
    if not docs:
        log_warning("No documents to add.")
        return

    store = get_vector_store()

    try:
        docs = _sanitize_docs(docs)

        total = 0
        for i in range(0, len(docs), batch_size):
            batch = docs[i : i + batch_size]

            ids: List[str] = []
            seen = set()

            for j, d in enumerate(batch):
                cid = _stable_chunk_id(d)

                # ultra-defensive: ensure uniqueness within the same upsert call
                if cid in seen:
                    cid = _sha1(cid + f"::dup::{i+j}")
                seen.add(cid)
                ids.append(cid)

            if len(ids) != len(set(ids)):
                raise RuntimeError(
                    "Internal error: duplicate IDs still present in batch"
                )

            store.add_documents(documents=batch, ids=ids)
            total += len(batch)
            log_info(f"Added batch {i // batch_size + 1}: {len(batch)} chunks")

        log_info(f"✅ Successfully ingested total {total} chunks")

    except Exception as e:
        log_error(f"Ingestion failed: {e}", exc_info=True)
        raise


def clear_collection() -> None:
    """Wipes the DB collection safely."""
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
    try:
        store = get_vector_store()
        return store._collection.count()
    except Exception as e:
        log_error(f"Count failed: {e}")
        return 0
