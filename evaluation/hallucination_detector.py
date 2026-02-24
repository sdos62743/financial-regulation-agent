# evaluation/hallucination_detector.py
"""
Hallucination Detector

This module detects hallucinations in the agent's generated response by 
comparing it against the retrieved source documents using an LLM-as-a-Judge approach.
"""

import logging

from langchain_core.prompts import PromptTemplate

from app.llm_config import get_llm
from observability.logger import log_info, log_error, log_debug, log_warning

from evaluation.prompts.loader import load_prompt

# LLM used as a strict judge - uses same provider as agent (LLM_PROVIDER env)
def _get_eval_llm():
    return get_llm().with_config(max_tokens=600)

# Load prompt from external file
hallucination_prompt =load_prompt("hallucination_detector")


async def detect_hallucinations(
    generated_response: str,
    retrieved_docs: list
) -> float:
    """
    Detect the level of hallucination in the generated response.

    Args:
        generated_response: The final answer produced by the agent
        retrieved_docs: List of documents used as grounding context

    Returns:
        Hallucination score between 0.0 (no hallucination) and 1.0 (severe hallucination)
    """
    if not generated_response or not retrieved_docs:
        log_warning("Missing response or sources for hallucination detection")
        return 0.5  # Neutral score when insufficient data

    log_debug(f"Hallucination detection started | Response length: {len(generated_response)}")

    # Prepare sources (limit length to avoid token overflow)
    sources_text = "\n\n".join(
        doc.get("page_content", "")[:750] for doc in retrieved_docs[:6]
    ) or "No source documents provided."

    try:
        chain = hallucination_prompt | _get_eval_llm()

        result = await chain.ainvoke({
            "response": generated_response,
            "sources": sources_text
        })

        output = result.content.strip().lower()

        # Parse hallucination score
        if "hallucination_score:" in output:
            try:
                score_str = output.split("hallucination_score:")[1].split()[0]
                score = float(score_str)
                score = max(0.0, min(1.0, score))  # Clamp to valid range
            except ValueError:
                score = 0.5
        else:
            score = 0.5

        log_info(f"Hallucination detection completed | Score: {score:.3f}")

        return score

    except Exception as e:
        log_error("Hallucination detection failed", exc_info=True)
        return 0.6  # Slightly conservative fallback