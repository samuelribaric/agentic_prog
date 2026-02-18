"""LangGraph state schema for the finance advisor agent."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


class FinanceState(TypedDict):
    """Shared state flowing through the LangGraph finance advisor graph."""

    # The original user query
    query: str

    # Chat message history (accumulates via operator.add)
    messages: Annotated[list[BaseMessage], operator.add]

    # Fetched account data (replaced on each data_fetch call)
    accounts: list[dict]

    # Raw transactions accumulated across tool calls
    transactions: Annotated[list[dict], operator.add]

    # Output from analyze node (plain-text categorization + calculations)
    analysis: str

    # Supervisor routing target: "data_fetch" | "analyze" | "advise" | "done"
    next_agent: str

    # Supervisor's reasoning and instructions for the next agent
    supervisor_notes: str

    # Final user-facing Markdown answer
    report: str

    # Safety counter — prevents infinite supervisor loops
    turn: int
