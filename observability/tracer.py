#!/usr/bin/env python3
"""
Request Tracer & Context Manager - Tier 1 Optimized
Manages high-performance correlation IDs using ContextVars.
"""

import uuid
from contextvars import ContextVar, Token
from typing import Optional

# Context variable to store the current request ID
# Using "unknown" as default ensures no log line ever has a null ID
request_id_var: ContextVar[str] = ContextVar("request_id", default="unknown")

def get_current_request_id() -> str:
    """
    Standalone accessor for the current request ID.
    Used by logger.py and nodes for high-speed lookups.
    """
    return request_id_var.get()

def set_request_id(request_id: Optional[str] = None) -> Token[str]:
    """
    Standalone setter for the request ID context.
    Generates a UUID4 if no ID is provided.
    """
    if not request_id:
        request_id = str(uuid.uuid4())
    return request_id_var.set(request_id)

class RequestTracer:
    """
    Unified Manager for request tracing and correlation.
    Provides a clean interface for the middleware and loggers.
    """

    @staticmethod
    def generate_request_id() -> str:
        """Utility to generate a new unique ID."""
        return str(uuid.uuid4())

    @staticmethod
    def set_request_id(request_id: Optional[str] = None) -> Token[str]:
        """Sets the current request ID and returns a reset token."""
        return set_request_id(request_id)

    @staticmethod
    def get_request_id() -> str:
        """Retrieves the current request ID from context."""
        return get_current_request_id()

    @staticmethod
    def reset_request_id(token: Token[str]) -> None:
        """
        Restores the previous request ID state.
        Critical for preventing context leakage in persistent worker threads.
        """
        try:
            request_id_var.reset(token)
        except Exception:
            # Handle cases where the token might have already been reset
            pass