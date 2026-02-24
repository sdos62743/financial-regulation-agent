# evaluation/metrics.py
"""
Metrics Calculator

This module computes aggregate evaluation metrics across multiple evaluation runs.
It calculates overall score and breakdowns for hallucination, answer quality,
and retrieval performance.
"""

import logging
from typing import Any, Dict, List

from observability.logger import log_info, log_warning

logger = logging.getLogger(__name__)


def calculate_metrics(evaluation_results: List[Dict]) -> Dict[str, float]:
    """
    Calculate comprehensive aggregate metrics from a list of evaluation results.

    Args:
        evaluation_results: List of dictionaries returned by evaluate_single_query()

    Returns:
        Dictionary with overall and per-category metrics
    """
    if not evaluation_results:
        log_warning("No evaluation results provided for metric calculation")
        return {"overall_score": 0.0, "total_evaluated": 0}

    total = len(evaluation_results)

    hallucination_scores = []
    answer_quality_scores = []
    retrieval_ndcg_scores = []
    validation_passed = 0

    for result in evaluation_results:
        eval_data = result.get("evaluation", {})

        # Hallucination (higher is better = less hallucination)
        hallucination_scores.append(1.0 - eval_data.get("hallucination_score", 0.5))

        # Answer Quality
        answer_quality_scores.append(
            eval_data.get("answer_quality", {}).get("score", 0.5)
        )

        # Retrieval Quality
        retrieval_ndcg_scores.append(
            eval_data.get("retrieval_metrics", {}).get("ndcg", 0.5)
        )

        # Validation count
        if eval_data.get("validation_result", False):
            validation_passed += 1

    # Compute averages
    avg_hallucination = sum(hallucination_scores) / total
    avg_answer_quality = sum(answer_quality_scores) / total
    avg_retrieval = sum(retrieval_ndcg_scores) / total

    # Weighted overall score
    overall_score = round(
        0.45 * avg_hallucination + 0.35 * avg_answer_quality + 0.20 * avg_retrieval, 4
    )

    metrics = {
        "overall_score": overall_score,
        "avg_hallucination_rate": round(1.0 - avg_hallucination, 4),
        "avg_answer_quality": round(avg_answer_quality, 4),
        "avg_retrieval_ndcg": round(avg_retrieval, 4),
        "validation_pass_rate": round(validation_passed / total, 4),
        "total_evaluated": total,
    }

    log_info(
        f"Metrics calculation completed | "
        f"Overall Score: {overall_score:.4f} | "
        f"Evaluated: {total} queries | "
        f"Validation Pass Rate: {metrics['validation_pass_rate']:.1%}"
    )

    return metrics
