#!/usr/bin/env python3
"""
Structured Logging - Tier 1 Async Optimized
Uses QueueHandler and a Safe Filter to prevent KeyError: 'request_id'.
"""

import logging
import logging.handlers
import sys
import queue
import os
from pathlib import Path
from typing import Any, Dict

# Safe import with fallback
try:
    from pythonjsonlogger import jsonlogger
    JSON_LOGGER_AVAILABLE = True
except ImportError:
    JSON_LOGGER_AVAILABLE = False

from .tracer import RequestTracer

# Use the specific name 'agent' for our application logs
logger = logging.getLogger("agent")

class RequestIDInterceptor(logging.Filter):
    """
    Safety Filter: Ensures 'request_id' exists on every LogRecord.
    This prevents KeyErrors when third-party libraries log without our extra dict.
    """
    def filter(self, record):
        if not hasattr(record, "request_id"):
            rid = RequestTracer.get_request_id()
            record.request_id = rid if (rid and rid != "unknown") else "system"
        return True

class CustomJsonFormatter(jsonlogger.JsonFormatter if JSON_LOGGER_AVAILABLE else logging.Formatter):
    """Safely injects request_id into JSON logs for file output."""
    def format(self, record):
        # Ensure request_id is present before JSON serialization
        if not hasattr(record, "request_id"):
            rid = RequestTracer.get_request_id()
            record.request_id = rid if (rid and rid != "unknown") else "system"
        return super().format(record)

def setup_structured_logging(log_level: int = logging.INFO) -> None:
    """Setup non-blocking logging with a background queue."""
    Path("logs").mkdir(exist_ok=True)

    # 1. Define the safety interceptor
    safety_filter = RequestIDInterceptor()

    # 2. Console Handler (Standard Output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(request_id)s | %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(safety_filter)

    # 3. File Handler (Rotating)
    log_file = "logs/agent.jsonl" if JSON_LOGGER_AVAILABLE else "logs/agent.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    
    if JSON_LOGGER_AVAILABLE:
        file_formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(module)s %(lineno)d %(request_id)s %(message)s"
        )
    else:
        file_formatter = console_formatter
    
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(safety_filter)

    # 4. Setup the Queue and QueueListener
    # Prevents disk I/O from blocking the main async loop
    log_queue = queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    
    listener = logging.handlers.QueueListener(
        log_queue, console_handler, file_handler, respect_handler_level=True
    )
    listener.start()

    # 5. Configure Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Clean up existing handlers
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    root_logger.addHandler(queue_handler)

    log_info(f"🚀 Logging stabilized (JSON: {JSON_LOGGER_AVAILABLE})")

# =============================================================================
# Helper & Convenience Functions
# =============================================================================

def _prepare_extra(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures request_id is injected into the extra dict."""
    extra = kwargs.get("extra", {})
    if "request_id" not in extra:
        extra["request_id"] = RequestTracer.get_request_id()
    
    # Merge remaining kwargs into extra
    reserved = ["exc_info", "stack_info", "extra"]
    for k, v in kwargs.items():
        if k not in reserved:
            extra[k] = v
    return extra

def log_debug(message: str, **kwargs: Any) -> None:
    """Logs at DEBUG level with request correlation."""
    logger.debug(message, extra=_prepare_extra(kwargs))

def log_info(message: str, **kwargs: Any) -> None:
    """Logs at INFO level with request correlation."""
    logger.info(message, extra=_prepare_extra(kwargs))

def log_warning(message: str, **kwargs: Any) -> None:
    """Logs at WARNING level with request correlation."""
    logger.warning(message, extra=_prepare_extra(kwargs))

def log_error(message: str, **kwargs: Any) -> None:
    """Logs at ERROR level with request correlation."""
    exc_info_val = kwargs.get("exc_info", False)
    logger.error(message, exc_info=exc_info_val, extra=_prepare_extra(kwargs))