# scripts/run_agent.py
"""
Interactive Chat Interface for Financial Regulation Agent
"""

import asyncio
import sys
import uuid
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from graph.builder import app as graph_app
from observability.logger import log_error, log_info


async def chat():
    """Interactive chat loop with the agent."""
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    print("\n" + "=" * 70)
    print("💬 Financial Regulation Agent - Interactive Chat")
    print(f"🆔 Session: {session_id}")
    print("=" * 70)
    print("Type your question below. Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            query = input("You: ").strip()

            if query.lower() in ["exit", "quit", "q"]:
                print("👋 Goodbye!")
                break

            if not query:
                continue

            print("🤖 Agent thinking...\n")
            log_info(f"Processing query: {query[:50]}...")

            result = await graph_app.ainvoke({"query": query}, config=config)

            response = result.get("synthesized_response") or result.get("generation")

            if response:
                print(f"Agent: {response}\n")
            else:
                print(
                    "Agent: I processed the request but no response was synthesized.\n"
                )

            if "documents" in result and result["documents"]:
                print(f"📚 Sources: {len(result['documents'])} documents used.")
                print("-" * 30 + "\n")

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            log_error(f"Chat Loop Error: {e}")
            print(f"❌ Error: {e}")
            print("Please try again.\n")


if __name__ == "__main__":
    try:
        asyncio.run(chat())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log_error(f"Fatal Startup Error: {e}")
        print(f"Fatal Error: {e}")
