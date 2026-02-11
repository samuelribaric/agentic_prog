"""Finalize node — uses deepseek-r1:8b to write the recommendation report."""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from state import ResearchState
from models import get_reasoning_model, strip_think_tags
from prompts import FINALIZE_SYSTEM, FINALIZE_HUMAN
from vector_store import query_benchmarks


def finalize_node(state: ResearchState) -> dict:
    """Generate the final Markdown recommendation report."""
    llm = get_reasoning_model()

    candidates_text = json.dumps(state.get("candidates", []), indent=2)

    # Retrieve benchmark data from vector store
    benchmarks = query_benchmarks(state["query"], k=5)
    benchmarks_text = "\n\n".join(benchmarks) if benchmarks else "No stored benchmarks."

    human_text = FINALIZE_HUMAN.format(
        query=state["query"],
        candidates=candidates_text,
        retrieved_benchmarks=benchmarks_text,
    )

    messages = [
        SystemMessage(content=FINALIZE_SYSTEM),
        HumanMessage(content=human_text),
    ]

    response = llm.invoke(messages)
    report = strip_think_tags(response.content)

    return {
        "report": report,
        "messages": [HumanMessage(content="Final report generated.")],
    }
