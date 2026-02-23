#!/usr/bin/env python3
"""
System & Agent Monitoring - Tier 1 Optimized
Non-blocking resource tracking and unified metrics aggregation.
"""

import logging
import psutil
from prometheus_client import Gauge, REGISTRY
from observability.logger import log_info, log_warning, log_error, log_debug

logger = logging.getLogger(__name__)

# =============================================================================
# Registry-Safe Metric Helper
# =============================================================================

def get_or_create_gauge(name, documentation):
    """
    Prevents DuplicateCollectorException. Synchronized with metrics.py.
    """
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Gauge(name, documentation)

# =============================================================================
# Prometheus Gauges
# =============================================================================

CPU_USAGE = get_or_create_gauge("system_cpu_usage_percent", "Current CPU usage")
MEMORY_USAGE = get_or_create_gauge("system_memory_usage_percent", "Current memory usage")
DISK_USAGE = get_or_create_gauge("system_disk_usage_percent", "Current disk usage")

ACTIVE_REQUESTS = get_or_create_gauge("agent_active_requests", "Currently active requests")
AVG_RESPONSE_TIME = get_or_create_gauge("agent_avg_response_time_seconds", "Avg response time")

# Unified with validation_node and metrics.py
HALLUCINATION_RATE = get_or_create_gauge("agent_hallucination_rate", "Current hallucination rate")
LATEST_OVERALL_SCORE = get_or_create_gauge("agent_evaluation_score", "Latest eval score")

class SystemMonitor:
    """Central monitoring utilities for Tier 1 performance."""

    @staticmethod
    def collect_system_metrics():
        """
        Non-blocking collection of system resource usage.
        Avoids interval=0.1 to prevent event loop lag.
        """
        try:
            # interval=None makes this non-blocking (returns since last call)
            cpu = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage("/").percent

            CPU_USAGE.set(cpu)
            MEMORY_USAGE.set(memory)
            DISK_USAGE.set(disk)

            # Log as debug to prevent Tier 1 log bloat
            log_debug(f"🖥️ [Monitor] CPU: {cpu}% | MEM: {memory}%")

            return {
                "cpu_percent": cpu,
                "memory_percent": memory,
                "disk_percent": disk,
            }
        except Exception as e:
            log_error(f"❌ [Monitor] System metrics failure: {e}")
            return {}

    @staticmethod
    def record_active_requests(count: int):
        """Updates the gauge for current concurrent users."""
        ACTIVE_REQUESTS.set(count)

    @staticmethod
    def record_response_time(duration_seconds: float):
        """Records the latency of the latest completed request."""
        AVG_RESPONSE_TIME.set(round(duration_seconds, 4))

    @staticmethod
    def record_evaluation_score(overall_score: float):
        """Synchronized recording for the synthesis/merge node."""
        LATEST_OVERALL_SCORE.set(round(overall_score, 4))

    @staticmethod
    def record_hallucination_rate(rate: float):
        """Synchronized recording for the critic/validation node."""
        HALLUCINATION_RATE.set(round(rate, 4))

    @staticmethod
    def get_system_health():
        """
        Health check utility for Kubernetes/Load Balancer probes.
        """
        metrics = SystemMonitor.collect_system_metrics()
        
        # Simple threshold logic for automated scaling
        is_pressed = metrics.get("cpu_percent", 0) > 85 or metrics.get("memory_percent", 0) > 85
        status = "degraded" if is_pressed else "healthy"
        
        if is_pressed:
            log_warning("⚠️ System health degraded: High resource pressure.")

        return {
            "status": status,
            **metrics
        }