"""LangGraph graph assembly + CLI entry point for the finance advisor agent."""

import sys

from langgraph.graph import StateGraph, START, END

from state import FinanceState
from nodes import supervisor_node, data_fetch_node, analyze_node, advise_node
import config


def _route_supervisor(state: FinanceState) -> str:
    """Read next_agent from state and route accordingly."""
    return state.get("next_agent", "done")


def build_graph() -> StateGraph:
    """Construct the finance advisor agent graph."""
    graph = StateGraph(FinanceState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("data_fetch", data_fetch_node)
    graph.add_node("analyze",    analyze_node)
    graph.add_node("advise",     advise_node)

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_supervisor,
        {
            "data_fetch": "data_fetch",
            "analyze":    "analyze",
            "advise":     "advise",
            "done":       END,
        },
    )
    graph.add_edge("data_fetch", "supervisor")
    graph.add_edge("analyze",    "supervisor")
    graph.add_edge("advise",     END)

    return graph


def main():
    if len(sys.argv) < 2:
        print("Usage: python researcher.py \"<your question>\"")
        print("Example: python researcher.py \"What did I spend on restaurants last month?\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"Finance query: {query}\n{'=' * 60}\n")

    graph = build_graph()
    app = graph.compile()

    initial_state: FinanceState = {
        "query":            query,
        "messages":         [],
        "accounts":         [],
        "transactions":     [],
        "analysis":         "",
        "next_agent":       "",
        "supervisor_notes": "",
        "report":           "",
        "turn":             0,
    }

    for event in app.stream(initial_state, stream_mode="updates"):
        for node_name, update in event.items():
            if node_name == "advise" and update.get("report"):
                print(f"\n{'=' * 60}")
                print("FINANCIAL ADVICE")
                print(f"{'=' * 60}\n")
                print(update["report"])
            elif node_name == "supervisor":
                notes = update.get("supervisor_notes", "")
                if notes:
                    print(f"[supervisor] {notes}")
            else:
                msgs = update.get("messages", [])
                for m in msgs:
                    print(f"[{node_name}] {m.content}")


if __name__ == "__main__":
    main()
