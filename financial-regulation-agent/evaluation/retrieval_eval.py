# evaluation/retrieval_eval.py
"""
Retrieval Quality Evaluator

This module evaluates how well the retrieved documents match the user's query 
and any available ground truth context using standard information retrieval metrics.
"""

import logging
from typing import List, Dict, Any

from langchain_core.documents import Document

from observability.logger import log_info, log_warning

logger = logging.getLogger(__name__)


def evaluate_retrieval(
    retrieved_docs: List[Document],
    ground_truth: str | None = None,
    k: int = 10
) -> Dict[str, float]:
    """
    Evaluate retrieval quality using standard information retrieval metrics.

    Args:
        retrieved_docs: List of documents returned by the RAG node
        ground_truth: Optional ground truth text for relevance calculation
        k: Number of top documents to consider for metrics (Precision@K, Recall@K, NDCG@K)

    Returns:
        Dictionary with retrieval metrics
    """
    if not retrieved_docs:
        log_warning("No documents retrieved for evaluation")
        return {
            "ndcg": 0.0,
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "num_retrieved": 0,
            "k": k
        }

    # Limit evaluation to top-k documents
    top_k_docs = retrieved_docs[:k]
    num_retrieved = len(top_k_docs)

    # Calculate relevance scores
    if ground_truth and ground_truth.strip():
        gt_words = set(ground_truth.lower().split())
        relevance_scores = []
        for doc in top_k_docs:
            doc_text = doc.page_content.lower()
            overlap = len(gt_words.intersection(set(doc_text.split()))) / max(len(gt_words), 1)
            relevance_scores.append(overlap)
    else:
        # No ground truth → assume all retrieved docs are relevant (optimistic baseline)
        relevance_scores = [1.0] * num_retrieved

    # NDCG@K (Normalized Discounted Cumulative Gain)
    dcg = sum(rel / (i + 1) for i, rel in enumerate(relevance_scores))
    idcg = sum(1.0 / (i + 1) for i in range(num_retrieved))
    ndcg = dcg / idcg if idcg > 0 else 0.0

    # Precision@K
    precision_at_k = sum(relevance_scores) / k if k > 0 else 0.0

    # Recall@K (simplified version based on available data)
    recall_at_k = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0

    metrics = {
        "ndcg": round(ndcg, 4),
        "precision_at_k": round(precision_at_k, 4),
        "recall_at_k": round(recall_at_k, 4),
        "num_retrieved": num_retrieved,
        "k": k
    }

    log_info(
        f"Retrieval evaluation completed | "
        f"NDCG@{k}: {metrics['ndcg']:.4f} | "
        f"Precision@{k}: {metrics['precision_at_k']:.4f}"
    )

    return metrics