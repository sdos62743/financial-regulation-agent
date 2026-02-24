# evaluation/evaluator.py
"""
Central Evaluation Orchestrator

Main entry point for running evaluations on the agent.
Supports single-query evaluation and full benchmark runs.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from langchain_core.documents import Document

from evaluation.answer_eval import evaluate_answer_quality
from evaluation.hallucination_detector import detect_hallucinations

# 1. Use Absolute Imports (Prevents "beyond top-level package" errors)
from evaluation.metrics import calculate_metrics
from evaluation.retrieval_eval import evaluate_retrieval
from observability.logger import log_error, log_info, log_warning

# Import monitoring and structured logging
from observability.monitor import SystemMonitor

# =============================================================================
# Standalone Bridge Function (Fixes the ImportError in merge.py)
# =============================================================================


async def evaluate_single_query(
    query: str,
    response: str,
    context: str | List[Document],
    request_id: str | None = None,
) -> Dict[str, Any]:
    """
    Standalone function used by the Graph Nodes (like merge.py).
    It initializes the evaluator and runs the single query check.
    """
    evaluator = AgentEvaluator()

    # Handle case where context is passed as a string (from a merged response)
    # or as a list of Documents (from a retrieval node)
    docs = context if isinstance(context, list) else []

    return await evaluator.evaluate_single_query(
        query=query,
        generated_answer=response,
        retrieved_docs=docs,
        request_id=request_id,
    )


# =============================================================================
# Core Evaluator Class
# =============================================================================


class AgentEvaluator:
    """Main evaluator for the Financial Regulation Agent."""

    def __init__(self, benchmark_path: str = "evaluation/benchmark_questions.json"):
        self.benchmark_path = Path(benchmark_path)
        self.benchmark_data = self._load_benchmark()

    def _load_benchmark(self) -> List[Dict]:
        """Load benchmark dataset with ground truth."""
        try:
            if not self.benchmark_path.exists():
                log_warning(f"Benchmark file not found: {self.benchmark_path}")
                return []
            with open(self.benchmark_path, encoding="utf-8") as f:
                data = json.load(f)
            log_info(f"Loaded {len(data)} benchmark questions")
            return data
        except Exception as e:
            log_error(f"Failed to load benchmark: {e}")
            return []

    async def evaluate_single_query(
        self,
        query: str,
        generated_answer: str,
        retrieved_docs: List[Document],
        ground_truth: str | None = None,
        request_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a single query comprehensively.
        """
        request_id = request_id or "unknown"
        log_info(f"[{request_id}] Evaluating single query")

        results = {}

        try:
            # 1. Hallucination Detection
            results["hallucination_score"] = await detect_hallucinations(
                generated_answer, retrieved_docs
            )

            # 2. Answer Quality
            results["answer_quality"] = await evaluate_answer_quality(
                query, generated_answer, ground_truth
            )

            # 3. Retrieval Quality
            if retrieved_docs:
                results["retrieval_metrics"] = evaluate_retrieval(
                    retrieved_docs, ground_truth
                )
            else:
                results["retrieval_metrics"] = {"ndcg": 0.0}

            # 4. Overall Score
            results["overall_score"] = self._compute_overall_score(results)

            # Record metrics for observability
            SystemMonitor.record_evaluation_score(results["overall_score"])
            SystemMonitor.record_hallucination_rate(results["hallucination_score"])

            log_info(
                f"[{request_id}] Evaluation completed | Overall Score: {results['overall_score']:.3f}"
            )

        except Exception as e:
            log_error(f"[{request_id}] Evaluation failed: {e}", exc_info=True)
            results["overall_score"] = 0.0
            results["error"] = str(e)

        return results

    def _compute_overall_score(self, results: Dict) -> float:
        """Compute weighted overall evaluation score."""
        hallucination = 1.0 - results.get("hallucination_score", 0.5)
        answer_quality = results.get("answer_quality", {}).get("score", 0.5)
        retrieval = results.get("retrieval_metrics", {}).get("ndcg", 0.5)

        return round(0.45 * hallucination + 0.35 * answer_quality + 0.20 * retrieval, 4)

    async def run_benchmark(self, agent_app, limit: int = 50) -> Dict:
        """Run full benchmark evaluation using the live agent."""
        log_info(
            f"Starting benchmark on {len(self.benchmark_data)} questions (limit={limit})"
        )

        results = []
        for i, item in enumerate(self.benchmark_data[:limit]):
            query = item.get("query", "")
            ground_truth = item.get("ground_truth")

            log_info(f"Evaluating [{i+1}/{min(limit, len(self.benchmark_data))}]")

            try:
                # Run full agent
                agent_output = await agent_app.ainvoke({"query": query})

                eval_result = await self.evaluate_single_query(
                    query=query,
                    generated_answer=agent_output.get("synthesized_response", ""),
                    retrieved_docs=agent_output.get("retrieved_docs", []),
                    ground_truth=ground_truth,
                )

                results.append(
                    {
                        "query": query,
                        "generated_answer": agent_output.get(
                            "synthesized_response", ""
                        ),
                        "evaluation": eval_result,
                    }
                )
            except Exception as e:
                log_error(f"Failed to evaluate query: {query[:80]}...", exc_info=True)

        final_metrics = calculate_metrics(results)

        log_info(
            f"Benchmark finished | Overall Score: {final_metrics.get('overall_score', 0):.4f}"
        )

        return {"overall_metrics": final_metrics, "detailed_results": results}
