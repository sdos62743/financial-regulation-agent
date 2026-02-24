# scripts/run_benchmark.py
"""
Run full benchmark evaluation on multiple questions.
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

    print("\n🚀 Starting benchmark evaluation...")
    print(f"Target Agent: LangGraph Regulatory Assistant (v2026)")
    print("-" * 50)

    results = await evaluator.run_benchmark(
        agent_app=graph_app,
        limit=20
    )

    print("\n" + "="*70)
    print("                🏆 BENCHMARK SUMMARY 🏆")
    print("="*70)

    metrics = results['overall_metrics']

    print(f"Overall Accuracy Score : {metrics['overall_score']:.4f}")
    print(f"Total Queries Tested   : {metrics['total_evaluated']}")
    print(f"Avg Hallucination Rate : {metrics['avg_hallucination_rate']:.1%}")
    print(f"Validation Pass Rate   : {metrics['validation_pass_rate']:.1%}")

    if metrics['validation_pass_rate'] < 0.80:
        print("\n⚠️  WARNING: Pass rate is below 80%. Check logs for reasoning node failures.")

    print("="*70)
    print("Evaluation Complete. Detailed results saved to results/ folder.\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBenchmark cancelled by user.")
