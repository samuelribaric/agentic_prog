"""Advise node — reasoning agent that writes the final user-facing Markdown response."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from state import FinanceState
from models import get_reasoning_model, strip_think_tags
from prompts import ADVISE_SYSTEM, ADVISE_HUMAN


def advise_node(state: FinanceState) -> dict:
    """Generate a clear, friendly financial advice response in Markdown."""
    llm = get_reasoning_model()

    analysis = state.get("analysis", "No analysis available.")

    human_text = ADVISE_HUMAN.format(
        query=state["query"],
        analysis=analysis,
    )

    messages = [
        SystemMessage(content=ADVISE_SYSTEM),
        HumanMessage(content=human_text),
    ]

    response = llm.invoke(messages)
    report = strip_think_tags(response.content)

    return {
        "report": report,
        "next_agent": "done",
        "messages": [HumanMessage(content="Financial advice report generated.")],
    }
