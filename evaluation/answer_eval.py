# evaluation/answer_eval.py
"""
Answer Quality Evaluator (LLM-as-a-Judge)

This module evaluates the quality of the agent's final generated answer 
using an LLM judge. It scores the answer on faithfulness, relevance, 
completeness, and clarity.
"""

import json
import logging
from typing import Dict, Any

from langchain_openai import ChatOpenAI
# FIX: Import from langchain_core to resolve ModuleNotFoundError
from langchain_core.prompts import PromptTemplate

from observability.logger import log_info, log_error, log_debug

from evaluation.prompts.loader import load_prompt

logger = logging.getLogger(__name__)

# LLM used as a strict judge for answer evaluation
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.0,          # Zero temperature for deterministic and consistent scoring
    max_tokens=700,
)

# Load prompt from external file
answer_eval_prompt = load_prompt("answer_eval")


async def evaluate_answer_quality(
    query: str,
    generated_answer: str,
    ground_truth: str | None = None
) -> Dict[str, Any]:
    """
    Evaluate the quality of the generated answer using LLM-as-a-Judge.

    This function assesses four key dimensions:
    - Faithfulness: How well the answer is grounded in sources
    - Relevance: How directly it addresses the query
    - Completeness: Whether it covers all important aspects
    - Clarity: How clear and professional the language is

    Args:
        query: Original user query
        generated_answer: Answer produced by the agent
        ground_truth: Optional reference answer for comparison

    Returns:
        Dictionary with detailed scores and feedback
    """
    log_debug(f"Answer quality evaluation started | Query: {query[:80]}...")

    try:
        chain = answer_eval_prompt | llm

        result = await chain.ainvoke({
            "query": query,
            "answer": generated_answer,
            "ground_truth": ground_truth or "No ground truth provided"
        })

        # Parse the JSON response from the LLM judge
        eval_data = json.loads(result.content.strip())

        score = float(eval_data.get("overall_score", 0.5))

        log_info(f"Answer quality evaluated | Overall Score: {score:.3f}")

        return {
            "score": score,
            "faithfulness": float(eval_data.get("faithfulness", 0.5)),
            "relevance": float(eval_data.get("relevance", 0.5)),
            "completeness": float(eval_data.get("completeness", 0.5)),
            "clarity": float(eval_data.get("clarity", 0.5)),
            "feedback": eval_data.get("feedback", "No feedback provided")
        }

    except json.JSONDecodeError:
        log_error("Failed to parse JSON from LLM judge")
        return _get_fallback_scores("Invalid JSON response from judge")

    except Exception as e:
        log_error("Answer quality evaluation failed", exc_info=True)
        return _get_fallback_scores("Unexpected error during evaluation")


def _get_fallback_scores(reason: str) -> Dict[str, Any]:
    """Return safe fallback scores when evaluation fails."""
    return {
        "score": 0.5,
        "faithfulness": 0.5,
        "relevance": 0.5,
        "completeness": 0.5,
        "clarity": 0.5,
        "feedback": reason
    }