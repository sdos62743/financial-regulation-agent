#!/usr/bin/env python3
"""
Central Configuration & Bootstrap - Tier 1 Optimized
Orchestrates environment loading and global observability settings.
Fixed for LangChain 0.3+ modularized imports.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

# FIXED: Moved from langchain.globals to langchain_core.globals
from langchain_core.globals import set_debug, set_verbose

# Direct imports for setup flow
from observability.logger import log_error, log_info, setup_structured_logging
from observability.tracer import RequestTracer


class Config:
    """Centralized configuration store to avoid multiple os.getenv calls."""

    BASE_DIR = Path(__file__).parent.parent
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # Provider Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # For Gemini 2.5 Flash

    # Application Settings
    PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT", "financial-regulation-agent")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    # Timeouts (seconds) - centralized for LLM, query controller, and Scrapy
    LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))
    QUERY_TIMEOUT = float(os.getenv("QUERY_TIMEOUT", "240"))
    DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "120"))

    # Rate limiting (e.g. "100/minute" per IP)
    RATE_LIMIT = os.getenv("RATE_LIMIT", "100/minute")

    @classmethod
    def as_dict(cls) -> Dict[str, Any]:
        """Returns config as dict for debugging or serialization."""
        return {
            k: v
            for k, v in cls.__dict__.items()
            if not k.startswith("__") and not callable(v)
        }


def load_environment() -> None:
    """Load environment variables with override priority."""
    env_path = Config.BASE_DIR / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        # In Tier 1, env vars may be injected via k8s/container orchestrator
        pass


def setup_langsmith() -> None:
    """Configure LangSmith for Tier 1 tracing."""
    api_key = os.getenv("LANGCHAIN_API_KEY")
    if api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = Config.PROJECT_NAME
        os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"

        set_debug(Config.DEBUG)
        # Using langchain_core.globals logic
        set_verbose(os.getenv("LANGCHAIN_VERBOSE", "false").lower() == "true")
        log_info("✅ LangSmith tracing enabled")
    else:
        os.environ["LANGCHAIN_TRACING_V2"] = "false"


def setup_environment() -> None:
    """
    Explicit entry point for application setup.
    Called by server.py or main.py.
    """
    load_environment()

    # Setup structured logging first for consistent log capture
    log_level = logging.DEBUG if Config.DEBUG else logging.INFO
    setup_structured_logging(log_level=log_level)

    setup_langsmith()

    # Initialize global request context for tracing
    RequestTracer.set_request_id("system-startup")

    # Production Sanity Checks
    _perform_startup_checks()


def _perform_startup_checks():
    """Validates presence of critical infrastructure keys."""
    log_info(f"🚀 Environment setup for: {Config.PROJECT_NAME}")

    # Updated to include Gemini requirements
    critical_keys = {
        "OPENAI_API_KEY": Config.OPENAI_API_KEY,
        "GOOGLE_API_KEY": Config.GOOGLE_API_KEY,
        "COHERE_API_KEY": Config.COHERE_API_KEY,
    }

    for name, val in critical_keys.items():
        if not val:
            # We log as warning instead of error to allow for selective model use
            log_error(f"⚠️  MISSING: {name} - Component using this provider will fail.")
        else:
            log_info(f"   {name:18}: Configured ✅")


# Side-effect free: setup_environment() must be called manually by entry points.
