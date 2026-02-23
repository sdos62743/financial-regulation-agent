# run_benchmark.py
"""
Run full benchmark evaluation on multiple questions.
"""

import asyncio
from evaluation.evaluator import AgentEvaluator
# Import your compiled app from the builder component we just finalized
from graph.builder import app as graph_app 

async def main():
    """
    Executes the evaluation framework against the LangGraph agent.
    """
    # The evaluator likely looks for 'benchmark_questions.json' in your data/ folder
    evaluator = AgentEvaluator()

    print("\n🚀 Starting benchmark evaluation...")
    print(f"Target Agent: LangGraph Regulatory Assistant (v2026)")
    print("-" * 50)
    
    # Use the compiled graph app we built
    results = await evaluator.run_benchmark(
        agent_app=graph_app,   
        limit=20               
    )

    # Output Formatting
    print("\n" + "="*70)
    print("                🏆 BENCHMARK SUMMARY 🏆")
    print("="*70)
    
    metrics = results['overall_metrics']
    
    # We display the core health metrics of the RAG system
    print(f"Overall Accuracy Score : {metrics['overall_score']:.4f}")
    print(f"Total Queries Tested   : {metrics['total_evaluated']}")
    print(f"Avg Hallucination Rate : {metrics['avg_hallucination_rate']:.1%}")
    print(f"Validation Pass Rate   : {metrics['validation_pass_rate']:.1%}")
    
    # Optional: Logic to flag if the agent is failing too often
    if metrics['validation_pass_rate'] < 0.80:
        print("\n⚠️  WARNING: Pass rate is below 80%. Check logs for reasoning node failures.")
    
    print("="*70)
    print("Evaluation Complete. Detailed results saved to results/ folder.\n")

if __name__ == "__main__":
    # Standard entry point for async execution
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBenchmark cancelled by user.")