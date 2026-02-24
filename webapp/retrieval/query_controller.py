#!/usr/bin/env python3
"""
RAG Query Controller - Tier 1 Production
Bridges FastAPI and LangGraph with explicit timeout protection.
Standardized for Python 3.11 and high-concurrency (300 RPM).
"""

import asyncio
import logging
import os
import traceback
from typing import Any, Dict

# Using the builder from your graph module
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

    async def ask(
        self,
        query: str,
        thread_id: str = "default",
        timeout: float = 60.0,  # Tier 1: 60s is standard; 120s is too slow for web
    ) -> Dict[str, Any]:
        """
        Process a user query through the full agent graph.
        Ensures the first step is 'classify_intent'.
        """
        query = query.strip()

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

        # Prepare initial state (Mapping keys for 2026 consistency)
        initial_state: AgentState = {
            "query": query,
            "intent": "classify_intent",  # Explicitly flagging the first logical step
            "plan": [],
            "documents": [],
            "tool_outputs": [],
            "response": "",
            "synthesized_response": "",
            "validation_result": False,
            "iterations": 0,
        }

        config = {"configurable": {"thread_id": thread_id}}

        try:
            # Tier 1 execution: use ainvoke for the full state return
            # wait_for ensures we don't hang the worker indefinitely
            result = await asyncio.wait_for(
                graph_app.ainvoke(initial_state, config=config), timeout=timeout
            )

            # Mapping logic to resolve the final response string
            final_answer = (
                result.get("synthesized_response")
                or result.get("response")
                or "I apologize, but I couldn't generate a specific answer. Please try rephrasing."
            )

            log_info(f"✅ [Controller] Graph Success | thread_id={thread_id}")

            return {
                "answer": final_answer,  # Renamed to 'answer' for index.html marked() compatibility
                "synthesized_response": final_answer,
                "documents": result.get("documents", []),
                "thread_id": thread_id,
                "success": True,
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

            # Tier 1: We return a clean error to the UI but keep the trace in the logs
            return {
                "error": f"Internal Engine Error: {str(e)}",
                "answer": "### System Error\nThe Intelligence Engine encountered a failure. Our team has been notified.",
                "traceback": error_trace if os.getenv("DEBUG") == "true" else None,
                "success": False,
            }
