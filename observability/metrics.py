#!/usr/bin/env python3
"""
Production Metrics & Monitoring - Tier 1 Optimized
Thread-safe Prometheus metrics for high-throughput async background tasks.
"""

import logging
import time
from typing import Callable

from fastapi import Request, Response
from prometheus_client import REGISTRY, Counter, Gauge, Histogram, make_asgi_app

from observability.logger import log_debug, log_error, log_info

logger = logging.getLogger(__name__)

# =============================================================================
# Registry-Safe Metric Helper
# =============================================================================


def get_or_create_metric(metric_class, name, documentation, labelnames=()):
    """
    Prevents DuplicateCollectorException during hot-reloads.
    """
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return metric_class(name, documentation, labelnames=labelnames)


# =============================================================================
# Prometheus Metrics
# =============================================================================

REQUEST_COUNT = get_or_create_metric(
    Counter, "agent_requests_total", "Total requests", ["endpoint", "status"]
)

REQUEST_LATENCY = get_or_create_metric(
    Histogram, "agent_request_latency_seconds", "Latency", ["endpoint"]
)

TOKEN_USAGE = get_or_create_metric(
    Counter, "agent_tokens_used_total", "Total tokens used", ["model", "component"]
)

EVALUATION_SCORE = get_or_create_metric(
    Gauge, "agent_evaluation_score", "Latest eval score", ["query_type"]
)

HALLUCINATION_RATE = get_or_create_metric(
    Gauge, "agent_hallucination_rate", "Hallucination rate"
)

ERROR_COUNT = get_or_create_metric(
    Counter, "agent_errors_total", "Total errors", ["error_type", "component"]
)

# =============================================================================
# High-Performance Recording Helpers
# =============================================================================


def record_token_usage(model: str, component: str, token_count: int):
    """
    Records token usage.
    Matches the signature used in graph/nodes/ to prevent background task crashes.
    """
    try:
        # Safety for missing labels
        m = model or "unknown_model"
        c = component or "unknown_node"
        t = token_count if isinstance(token_count, (int, float)) else 0

        TOKEN_USAGE.labels(model=m, component=c).inc(t)

        # PERF: Only log at debug level to keep the event loop fast
        log_debug(f"📊 [Metrics] {c} used {t} tokens ({m})")
    except Exception as e:
        # Fail silently in metrics to ensure the main Agent logic never stops
        pass


def record_evaluation_score(overall_score: float, query_type: str = "general"):
    """Records the latest evaluation score."""
    try:
        EVALUATION_SCORE.labels(query_type=query_type).set(overall_score)
        # Using debug here because high-frequency logs can slow down Tier 1
        log_debug(f"📈 [Metrics] Eval score for {query_type}: {overall_score}")
    except Exception:
        pass


def record_hallucination_rate(rate: float):
    """Records hallucination check results."""
    try:
        HALLUCINATION_RATE.set(rate)
    except Exception:
        pass


# =============================================================================
# Middleware
# =============================================================================


def observe_request_middleware(app):
    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next: Callable):
        if request.url.path == "/metrics":
            return await call_next(request)

        start_time = time.perf_counter()
        endpoint = request.url.path

        try:
            response: Response = await call_next(request)
            REQUEST_COUNT.labels(endpoint=endpoint, status=response.status_code).inc()
            return response
        except Exception as e:
            REQUEST_COUNT.labels(endpoint=endpoint, status="error").inc()
            ERROR_COUNT.labels(error_type=type(e).__name__, component="fastapi").inc()
            raise
        finally:
            latency = time.perf_counter() - start_time
            REQUEST_LATENCY.labels(endpoint=endpoint).observe(latency)


# Prometheus metrics endpoint
metrics_app = make_asgi_app()
