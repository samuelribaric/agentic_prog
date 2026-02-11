"""Retrieve node — stores benchmarks in ChromaDB and queries for comparisons."""

from langchain_core.messages import HumanMessage

from state import ResearchState
from vector_store import store_benchmarks, query_benchmarks


def retrieve_node(state: ResearchState) -> dict:
    """Store new benchmark data and retrieve relevant comparisons."""
    candidates = state.get("candidates", [])

    # Store any new candidate benchmarks
    store_benchmarks(candidates)

    # Query for relevant benchmark comparisons
    retrieved = query_benchmarks(state["query"], k=5)
    retrieved_text = "\n\n".join(retrieved) if retrieved else "No benchmark data available."

    return {
        "messages": [HumanMessage(content=f"Retrieved {len(retrieved)} benchmark entries from vector store.")],
        "search_results": [f"[ChromaDB Benchmarks]\n{retrieved_text}"],
    }
