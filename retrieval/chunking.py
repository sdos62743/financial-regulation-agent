#!/usr/bin/env python3
"""
Optimized text chunking utilities for regulatory documents - Tier 1 2026.
Standardized to use the project-wide embedding provider for semantic consistency.
"""

from typing import Literal

from langchain_experimental.text_splitter import SemanticChunker

# Correct imports for LangChain >= 0.3
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.llm_config import get_embeddings
from observability.logger import log_info, log_warning


def get_text_splitter(
    method: Literal["recursive", "semantic"] = "recursive",
    chunk_size: int = 1200,
    chunk_overlap: int = 200,
):
    """
    Returns a configured text splitter optimized for regulatory/legal text.
    Ensures semantic consistency by using the locked Gemini/OpenAI provider.
    """
    log_info(f"✂️ [Chunking] Initializing {method} splitter | size: {chunk_size}")

    if method == "recursive":
        # Recursive splitter tuned for high-fidelity legal structures
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=[
                "\n\n",  # Paragraphs
                "\n",  # Lines
                "\n(a)",  # Common legal subsections
                "\n(b)",
                "\n(c)",
                "\n(1)",  # Numbered lists
                "\n(2)",
                ". ",  # Sentences
                "; ",  # Clauses
                ", ",  # Phrasing
                " ",  # Words
                "",
            ],
            length_function=len,
            is_separator_regex=False,
        )

    elif method == "semantic":
        # TIER 1 ALIGNMENT: Use the global embedding model from llm_config
        # This ensures that the way the document is "broken" matches the way it is "searched"
        try:
            embeddings = get_embeddings()
            return SemanticChunker(
                embeddings=embeddings,
                breakpoint_threshold_type="percentile",
                breakpoint_threshold_amount=90,
            )
        except Exception as e:
            log_warning(
                f"⚠️ Failed to init semantic embeddings ({e}). Falling back to recursive."
            )
            return RecursiveCharacterTextSplitter(
                chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )

    else:
        log_warning(f"❓ Unknown method '{method}'. Falling back to recursive.")
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
