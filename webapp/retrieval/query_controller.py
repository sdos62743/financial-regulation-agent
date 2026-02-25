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

from graph.builder import app as graph_app
from graph.state import AgentState
from observability.logger import log_error, log_info, log_warning


class RAGController:
    """
    Singleton controller for invoking the Financial Regulation Agent graph.
    Maintains graph instance efficiency across web requests.
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
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        query = (query or "").strip()

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
            "intent": "classify_intent",
            "plan": [],
            "filters": {},  # ✅ required by state
            "retrieved_docs": [],  # ✅ correct key
            "tool_outputs": [],
            "response": "",
            "synthesized_response": "",
            "validation_result": False,
            "iterations": 0,
            "final_output": "",
        }
        config = {"configurable": {"thread_id": thread_id}}

        try:
            result = await asyncio.wait_for(
                graph_app.ainvoke(initial_state, config=config),
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
            error_trace = traceback.format_exc()
            log_error(f"❌ [Controller] Graph Failure: {str(e)}", thread_id=thread_id)
            return {
                "error": f"Internal Engine Error: {str(e)}",
                "answer": "### System Error\nThe Intelligence Engine encountered a failure. Our team has been notified.",
                "traceback": error_trace if os.getenv("DEBUG") == "true" else None,
                "success": False,
            }
