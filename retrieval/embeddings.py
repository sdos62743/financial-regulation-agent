#!/usr/bin/env python3
"""
Embedding Service - Tier 1 2026 Optimized (LangChain Compatible)

Fixes:
- Adds async methods (aembed_query / aembed_documents)
- Uses underlying.embed_documents for batching when possible
- Atomic cache writes + best-effort file locking
- Handles corrupted cache entries gracefully
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from typing import TYPE_CHECKING, List, Optional

from app.config import Config
from app.llm_config import get_embeddings as get_stable_embeddings
from observability.logger import log_error, log_info, log_warning

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write_json(path: str, data) -> None:
    """Write JSON atomically (write temp then replace)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="emb_", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)  # atomic on POSIX + Windows
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


class FileCachedEmbeddings:
    """
    File-based embedding cache wrapper.

    Compatible with LangChain expectations:
    - embed_query / embed_documents
    - aembed_query / aembed_documents (async)
    """

    def __init__(self, underlying: Embeddings, cache_dir: str, namespace: str):
        self.underlying = underlying
        self.cache_dir = os.path.join(cache_dir, namespace)
        os.makedirs(self.cache_dir, exist_ok=True)

    def _path_for_text(self, text: str) -> str:
        return os.path.join(self.cache_dir, f"{_hash_text(text)}.json")

    def _lock_path(self, path: str) -> str:
        return path + ".lock"

    def _read_cache(self, path: str) -> Optional[List[float]]:
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # minimal validation
            if isinstance(data, list) and data and isinstance(data[0], (int, float)):
                return data
        except Exception:
            log_warning(f"⚠️ Corrupted embedding cache entry: {path} (will recompute)")
        return None

    def _acquire_lock(self, lock_path: str) -> bool:
        """
        Best-effort lock using O_EXCL lockfile.
        Returns True if acquired, False otherwise.
        """
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            return False
        except Exception:
            # if locking fails for any reason, just proceed without it
            return False

    def _release_lock(self, lock_path: str) -> None:
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass

    def embed_query(self, text: str) -> List[float]:
        path = self._path_for_text(text)
        cached = self._read_cache(path)
        if cached is not None:
            return cached

        lock_path = self._lock_path(path)
        got_lock = self._acquire_lock(lock_path)
        try:
            # another process might have written it while we waited
            cached = self._read_cache(path)
            if cached is not None:
                return cached

            emb = self.underlying.embed_query(text)
            _atomic_write_json(path, emb)
            return emb
        finally:
            if got_lock:
                self._release_lock(lock_path)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # Fast path: all cached?
        paths = [self._path_for_text(t) for t in texts]
        cached: List[Optional[List[float]]] = [self._read_cache(p) for p in paths]

        missing_idx = [i for i, c in enumerate(cached) if c is None]
        if not missing_idx:
            return [c for c in cached if c is not None]  # type: ignore[return-value]

        # Batch embed missing texts using underlying if available
        missing_texts = [texts[i] for i in missing_idx]

        try:
            # Most providers implement embed_documents efficiently
            new_embs = self.underlying.embed_documents(missing_texts)
        except Exception:
            # Fallback: query one-by-one
            new_embs = [self.underlying.embed_query(t) for t in missing_texts]

        # Write missing to cache (atomic)
        for i, emb in zip(missing_idx, new_embs):
            p = paths[i]
            lock_path = self._lock_path(p)
            got_lock = self._acquire_lock(lock_path)
            try:
                # don't overwrite if someone else wrote it
                if self._read_cache(p) is None:
                    _atomic_write_json(p, emb)
            finally:
                if got_lock:
                    self._release_lock(lock_path)

            cached[i] = emb

        return [c for c in cached if c is not None]  # type: ignore[return-value]

    # --------------------
    # Async wrappers
    # --------------------
    async def aembed_query(self, text: str) -> List[float]:
        return await asyncio.to_thread(self.embed_query, text)

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        return await asyncio.to_thread(self.embed_documents, texts)


def get_embeddings(cache: bool = True) -> "Embeddings":
    """
    Returns the version-locked embedding model with optional file caching.
    """
    try:
        embeddings = get_stable_embeddings()

        model_attr = getattr(
            embeddings,
            "model",
            getattr(embeddings, "model_name", "default"),
        )

        log_info(f"🔢 Initializing Ingestion Embeddings | Source: {model_attr}")

        if not cache:
            return embeddings

        project_root = Config.BASE_DIR
        cache_root = os.path.join(project_root, "data", "cache", "embeddings")
        os.makedirs(cache_root, exist_ok=True)

        namespace = f"fin_reg_{str(model_attr).replace('/', '_')}"

        cached_embeddings = FileCachedEmbeddings(
            underlying=embeddings,
            cache_dir=cache_root,
            namespace=namespace,
        )

        log_info(f"✅ Embedding cache active: {cache_root} | Namespace: {namespace}")
        return cached_embeddings

    except Exception as e:
        log_error(f"❌ Failed to initialize ingestion embeddings: {e}")
        raise