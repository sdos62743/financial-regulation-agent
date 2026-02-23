# run_agent.py
"""
Interactive Chat Interface for Financial Regulation Agent
"""

import asyncio
import sys
import uuid
from pathlib import Path

# Add project root to path for absolute imports
sys.path.insert(0, str(Path(__file__).parent))

from graph.builder import app as graph_app
from observability.logger import log_info, log_error

async def chat():
    """Interactive chat loop with the agent."""
    # Generate a unique session ID for this chat instance
    # This allows the graph to maintain memory across turns
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    print("\n" + "="*70)
    print("💬 Financial Regulation Agent - Interactive Chat")
    print(f"🆔 Session: {session_id}")
    print("="*70)
    print("Type your question below. Type 'exit' or 'quit' to stop.\n")

    while True:
        try:
            # Use standard input for terminal interaction
            query = input("You: ").strip()

            if query.lower() in ["exit", "quit", "q"]:
                print("👋 Goodbye!")
                break

            if not query:
                continue

            print("🤖 Agent thinking...\n")
            log_info(f"Processing query: {query[:50]}...")

            # Invoke the graph asynchronously
            # Note: We pass the query in the state and the config for memory
            result = await graph_app.ainvoke(
                {"query": query}, 
                config=config
            )

            # Extract the response from your graph's state
            response = result.get("synthesized_response") or result.get("generation")
            
            if response:
                print(f"Agent: {response}\n")
            else:
                print("Agent: I processed the request but no response was synthesized.\n")

            # Show sources if the graph provides them
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
        # Proper async entry point for Python 3.13
        asyncio.run(chat())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log_error(f"Fatal Startup Error: {e}")
        print(f"Fatal Error: {e}")