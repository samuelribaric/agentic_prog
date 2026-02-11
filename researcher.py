"""LangGraph graph assembly + CLI entry point for the research agent."""

import sys

from langgraph.graph import StateGraph, START, END

from state import ResearchState
from nodes import search_node, reflect_node, retrieve_node, finalize_node
import config


def should_continue(state: ResearchState) -> str:
    """Conditional edge: loop back to search or proceed to retrieve."""
    if not state.get("research_complete", False) and state.get("iteration", 0) < config.MAX_SEARCH_ITERATIONS:
        return "search"
    return "retrieve"


def build_graph() -> StateGraph:
    """Construct the research agent graph."""
    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("search", search_node)
    graph.add_node("reflect", reflect_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("finalize", finalize_node)

    # Define edges: START → search → reflect → [conditional] → retrieve → finalize → END
    graph.add_edge(START, "search")
    graph.add_edge("search", "reflect")
    graph.add_conditional_edges("reflect", should_continue, {"search": "search", "retrieve": "retrieve"})
    graph.add_edge("retrieve", "finalize")
    graph.add_edge("finalize", END)

    return graph


def main():
    if len(sys.argv) < 2:
        print("Usage: python researcher.py \"<your query>\"")
        print("Example: python researcher.py \"I need a model for code generation under $0.01/1K tokens\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"Researching: {query}\n{'=' * 60}\n")

    graph = build_graph()
    app = graph.compile()

    initial_state: ResearchState = {
        "query": query,
        "messages": [],
        "search_results": [],
        "candidates": [],
        "gaps": [],
        "research_complete": False,
        "iteration": 0,
        "report": "",
    }

    # Stream events to show progress
    for event in app.stream(initial_state, stream_mode="updates"):
        for node_name, update in event.items():
            if node_name == "finalize" and "report" in update:
                print(f"\n{'=' * 60}")
                print("FINAL RECOMMENDATION REPORT")
                print(f"{'=' * 60}\n")
                print(update["report"])
            else:
                # Show progress messages
                msgs = update.get("messages", [])
                for m in msgs:
                    print(f"[{node_name}] {m.content}")


if __name__ == "__main__":
    main()
