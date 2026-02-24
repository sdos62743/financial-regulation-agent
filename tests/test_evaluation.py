# tests/test_evaluation.py
"""
Production tests for the Evaluation Framework.

Tests cover:
- Single query evaluation
- Hallucination detection
- Answer quality scoring
- Retrieval metrics
- Overall metrics calculation
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.documents import Document

from evaluation.answer_eval import evaluate_answer_quality
from evaluation.evaluator import AgentEvaluator
from evaluation.hallucination_detector import detect_hallucinations
from evaluation.metrics import calculate_metrics


@pytest.fixture
def sample_documents():
    return [
        Document(
            page_content="The Federal Reserve raised the federal funds rate by 25 basis points."
        ),
        Document(
            page_content="Inflation has moderated but remains above the 2% target."
        ),
    ]


@pytest.fixture
def sample_evaluator():
    evaluator = AgentEvaluator(benchmark_path="evaluation/benchmark_questions.json")
    return evaluator


@pytest.mark.asyncio
async def test_hallucination_detection():
    """Test hallucination detector with and without hallucination"""
    good_response = (
        "The FOMC raised rates by 25 bps as stated in the June 2023 statement."
    )
    bad_response = "The FOMC cut rates by 50 bps in June 2023."

    score_good = await detect_hallucinations(good_response, sample_documents())
    score_bad = await detect_hallucinations(bad_response, sample_documents())

    assert 0.0 <= score_good <= 0.3  # Should have low hallucination score
    assert (
        score_bad > score_good
    )  # Bad response should score higher (more hallucinated)


@pytest.mark.asyncio
async def test_answer_quality_evaluation():
    """Test answer quality evaluator"""
    query = "What was the FOMC decision in June 2023?"
    good_answer = "The FOMC raised the target federal funds rate by 25 basis points."
    bad_answer = "The FOMC decided to cut rates dramatically."

    result = await evaluate_answer_quality(query, good_answer)

    assert "score" in result
    assert 0.0 <= result["score"] <= 1.0
    assert "feedback" in result


def test_metrics_calculation():
    """Test aggregate metrics calculation"""
    sample_results = [
        {
            "evaluation": {
                "hallucination_score": 0.1,
                "answer_quality": {"score": 0.85},
                "retrieval_metrics": {"ndcg": 0.92},
                "validation_result": True,
            }
        },
        {
            "evaluation": {
                "hallucination_score": 0.6,
                "answer_quality": {"score": 0.45},
                "retrieval_metrics": {"ndcg": 0.65},
                "validation_result": False,
            }
        },
    ]

    metrics = calculate_metrics(sample_results)

    assert "overall_score" in metrics
    assert 0.0 <= metrics["overall_score"] <= 1.0
    assert metrics["total_evaluated"] == 2
    assert "validation_pass_rate" in metrics


@pytest.mark.asyncio
async def test_evaluator_single_query(sample_evaluator):
    """Test single query evaluation"""
    result = await sample_evaluator.evaluate_single_query(
        query="What is the current Fed Funds Rate?",
        generated_answer="The current Fed Funds Rate is 5.25%.",
        retrieved_docs=sample_documents(),
        ground_truth="The Fed Funds Rate is 5.25% as of July 2023.",
    )

    assert "overall_score" in result
    assert "hallucination_score" in result
    assert "answer_quality" in result


@pytest.mark.asyncio
async def test_benchmark_run(sample_evaluator):
    """Test running the full benchmark (with limit to keep test fast)"""
    # Mock the agent to avoid calling real graph
    mock_agent = AsyncMock()
    mock_agent.ainvoke.return_value = {
        "synthesized_response": "Test answer",
        "retrieved_docs": sample_documents(),
    }

    result = await sample_evaluator.run_benchmark(mock_agent, limit=3)

    assert "overall_metrics" in result
    assert "detailed_results" in result
    assert len(result["detailed_results"]) <= 3
