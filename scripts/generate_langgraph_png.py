#!/usr/bin/env python3
"""
Generate langgraph.png from the compiled LangGraph.
Uses mermaid.ink API (requires network) or pygraphviz (requires: brew install graphviz, pip install pygraphviz).
"""
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.builder import app


def main():
    output = Path(__file__).parent.parent / "langgraph.png"
    g = app.get_graph()

    # 1. Try draw_png (pygraphviz) - fastest if available
    try:
        result = g.draw_png(output_file_path=str(output))
        if result or output.exists():
            print(f"✅ Generated {output} (pygraphviz)")
            return 0
    except ImportError:
        pass

    # 2. Try draw_mermaid_png (mermaid.ink API)
    try:
        from langchain_core.runnables.graph_mermaid import MermaidDrawMethod

        result = g.draw_mermaid_png(
            output_file_path=str(output),
            draw_method=MermaidDrawMethod.API,
            max_retries=3,
            retry_delay=2.0,
        )
        if result and output.exists():
            print(f"✅ Generated {output} (mermaid.ink)")
            return 0
    except Exception as e:
        print(f"⚠️ mermaid.ink failed: {e}")

    # 3. Fallback: save mermaid source for manual rendering
    mermaid_path = output.with_suffix(".mmd")
    mermaid = g.draw_mermaid()
    mermaid_path.write_text(mermaid, encoding="utf-8")
    print(f"⚠️ Could not generate PNG. Saved Mermaid to {mermaid_path}")
    print("   Render at https://mermaid.live or run: brew install graphviz && pip install pygraphviz")
    return 1


if __name__ == "__main__":
    sys.exit(main())
