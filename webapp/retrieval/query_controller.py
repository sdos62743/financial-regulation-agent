#!/usr/bin/env python3
"""
RAG Query Controller - Tier 1 Production
Bridges FastAPI and LangGraph with explicit timeout protection.
Standardized for Python 3.11 and high-concurrency (300 RPM).
"""

import asyncio
import os
import traceback
from typing import Any, Dict

from app.config import Config
from graph.builder import app as graph_app
from graph.state import AgentState
from observability.logger import log_error, log_info, log_warning

RATE_LIMIT_INDICATORS = (
    "429",
    "resource_exhausted",
    "rate limit",
    "quota exceeded",
    "too many requests",
    "RESOURCE_EXHAUSTED",
)


def _is_rate_limit_error(exc: BaseException) -> bool:
    """Detect rate limit / quota errors from LLM providers (Gemini, OpenAI, etc.)."""
    msg = str(exc).lower()
    name = type(exc).__name__.lower()
    for indicator in RATE_LIMIT_INDICATORS:
        if indicator.lower() in msg or indicator.lower() in name:
            return True
    # Check wrapped cause (e.g., LangChain wraps provider errors)
    cause = getattr(exc, "__cause__", None) or getattr(exc, "cause", None)
    if cause:
        return _is_rate_limit_error(cause)
    return False


class RAGController:
    """
    Singleton controller for invoking the Financial Regulation Agent graph.
    Maintains graph instance efficiency across web requests.

    Note (streaming vs ainvoke): The main API (/query) uses astream_events for
    streaming. This webapp uses ainvoke with timeout for simpler request/response
    semantics. For long queries, consider adding streaming support here.
    """

    def __init__(self):
        log_info("🚀 [Controller] RAGController initialized - LangGraph engine ready")

    @staticmethod
    def _pick_final_answer(result: Dict[str, Any]) -> str:
        """
        Canonical answer selection.
        Prefer final_output (LangGraph terminal output), then synthesized_response, then response.
        """
        for key in ("final_output", "synthesized_response", "response"):
            val = result.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()

        return "I apologize, but I couldn't generate a specific answer. Please try rephrasing."

    async def ask(
        self,
        query: str,
        thread_id: str = "default",
        timeout: float | None = None,
    ) -> Dict[str, Any]:
        query = (query or "").strip()

        timeout = timeout if timeout is not None else Config.QUERY_TIMEOUT

        if not query:
            log_warning("⚠️ [Controller] Empty query received")
            return {"error": "Query cannot be empty", "success": False}

        if len(query) > 2000:
            log_warning(f"⚠️ [Controller] Query too long: {len(query)} chars")
            return {
                "error": "Query is too long (maximum 2000 characters)",
                "success": False,
            }

        log_info(
            f"🧠 [Controller] Invoking Graph | thread_id={thread_id} | query='{query[:50]}...'"
        )

        initial_state: AgentState = {
            "query": query,
            "intent": "other",
            "plan": [],
            "filters": {},
            "retrieved_docs": [],
            "tool_outputs": [],
            "synthesized_response": "",
            "validation_result": False,
            "iterations": 0,
            "final_output": "",
        }
        config = {"configurable": {"thread_id": thread_id}}

        try:
            result = await asyncio.wait_for(
                graph_app.ainvoke(initial_state, config=config),  # type: ignore[arg-type]
                timeout=timeout,
            )

            final_answer = self._pick_final_answer(result)

            # If the graph produced any non-empty answer string, it's success,
            # even if validation_result=False (clarifying question path).
            success = bool(final_answer and final_answer.strip())
            # Optionally keep validation_result exposed for UI/debug:
            validation = bool(result.get("validation_result", False))

            log_info(f"✅ [Controller] Graph Success | thread_id={thread_id}")

            return {
                "answer": final_answer,
                "final_output": result.get("final_output", ""),
                "synthesized_response": result.get("synthesized_response", ""),
                "response": result.get("response", ""),
                "validation_result": validation,
                "thread_id": thread_id,
                "success": success,
            }
        except asyncio.TimeoutError:
            log_error(
                f"⏱️ [Controller] Timeout after {timeout}s | thread_id={thread_id}"
            )
            return {
                "error": "The analysis took too long for a live response. Please try a narrower query.",
                "answer": "**Timeout Error:** Analysis limit reached.",
                "success": False,
            }

        except Exception as e:
            if _is_rate_limit_error(e):
                log_error(
                    f"⚠️ [Controller] Rate limit / quota exceeded | thread_id={thread_id}"
                )
                return {
                    "error": "The service is temporarily at capacity. Please try again in a few minutes.",
                    "answer": "**Service temporarily unavailable.** Please try again shortly.",
                    "success": False,
                }
            error_trace = traceback.format_exc()
            log_error(f"❌ [Controller] Graph Failure: {str(e)}", thread_id=thread_id)
            return {
                "error": f"Internal Engine Error: {str(e)}",
                "answer": "### System Error\nThe Intelligence Engine encountered a failure. Our team has been notified.",
                "traceback": error_trace if os.getenv("DEBUG") == "true" else None,
                "success": False,
            }
