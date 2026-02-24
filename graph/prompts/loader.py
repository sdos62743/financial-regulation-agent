#!/usr/bin/env python3
"""
Performance Optimized Prompt Loader
Uses LRU caching to eliminate disk I/O latency after the first load.
"""

from functools import lru_cache
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from observability.logger import log_error, log_info


@lru_cache(maxsize=32)
def load_prompt(name: str) -> ChatPromptTemplate:
    """
    Loads a prompt from the filesystem and caches it in memory.
    Subsequent calls for the same 'name' return instantly from RAM.
    """
    base_path = Path(__file__).parent

    # Prioritize .txt for simple templates, .yaml for complex ones
    extensions = [".txt", ".yaml", ".json"]
    prompt_file = None

    for ext in extensions:
        potential_path = base_path / f"{name}{ext}"
        if potential_path.exists():
            prompt_file = potential_path
            break

    if not prompt_file:
        error_msg = f"Prompt file not found: {name} in {base_path}"
        log_error(error_msg)
        raise FileNotFoundError(error_msg)

    try:
        # read_text is synchronous and slow; caching makes this run only once per prompt
        template_text = prompt_file.read_text(encoding="utf-8").strip()

        prompt = ChatPromptTemplate.from_messages(
            [("system", template_text), ("human", "{query}")]
        )

        # log_info inside a cached function only triggers on the FIRST load
        log_info(f"🆕 [Loader] Cache miss - Loaded from disk: {prompt_file.name}")
        return prompt

    except Exception as e:
        log_error(f"Error building template from {name}: {e}")
        # We don't want to cache a failed load, but lru_cache will cache it
        # unless we raise. Raising is correct here.
        raise
