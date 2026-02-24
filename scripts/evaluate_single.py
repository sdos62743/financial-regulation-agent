# scripts/evaluate_single.py
"""
Quick script to evaluate a single query using your agent.
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

from evaluation.evaluator import AgentEvaluator
from graph.builder import app as graph_app

async def main():
    evaluator = AgentEvaluator()

    query = "What did the FOMC say about interest rates in 2023?"

    # Run the full agent
    print("Running agent...")
    result = await graph_app.ainvoke({"query": query})

    # Evaluate the result
    print("Evaluating response...")
    eval_result = await evaluator.evaluate_single_query(
        query=query,
        generated_answer=result.get("synthesized_response", ""),
        retrieved_docs=result.get("retrieved_docs", []),
        ground_truth=None,
    )

    print("\n" + "="*60)
    print("EVALUATION RESULT")
    print("="*60)
    print(f"Overall Score     : {eval_result['overall_score']:.3f}")
    print(f"Hallucination     : {eval_result['hallucination_score']:.3f}")
    print(f"Answer Quality    : {eval_result['answer_quality']['score']:.3f}")
    print(f"Feedback          : {eval_result['answer_quality']['feedback']}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
