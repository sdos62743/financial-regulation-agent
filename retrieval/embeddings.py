#!/usr/bin/env python3
"""
Embedding Service - Tier 1 2026 Optimized (LangChain 1.x Compatible)
"""

from __future__ import annotations
import os
import json
import hashlib
from typing import TYPE_CHECKING, List

from app.config import Config
from app.llm_config import get_embeddings as get_stable_embeddings
from observability.logger import log_error, log_info

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings


def _hash_text(text: str) -> str:
    """Create deterministic hash for caching."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FileCachedEmbeddings:
    """
    Application-layer embedding cache compatible with LangChain 1.x
    """

    def __init__(self, underlying: Embeddings, cache_dir: str, namespace: str):
        self.underlying = underlying
        self.cache_dir = os.path.join(cache_dir, namespace)
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_cache_path(self, text: str) -> str:
        return os.path.join(self.cache_dir, f"{_hash_text(text)}.json")

    def embed_query(self, text: str) -> List[float]:
        path = self._get_cache_path(text)

        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)

        embedding = self.underlying.embed_query(text)

        with open(path, "w") as f:
            json.dump(embedding, f)

        return embedding

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        results = []
        for text in texts:
            results.append(self.embed_query(text))
        return results


def get_embeddings(cache: bool = True) -> Embeddings:
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

        namespace = f"fin_reg_{model_attr.replace('/', '_')}"

        cached_embeddings = FileCachedEmbeddings(
            underlying=embeddings,
            cache_dir=cache_root,
            namespace=namespace,
        )

        log_info(
            f"✅ Embedding cache active: {cache_root} | Namespace: {namespace}"
        )

        return cached_embeddings

    except Exception as e:
        log_error(f"❌ Failed to initialize ingestion embeddings: {e}")
        raise