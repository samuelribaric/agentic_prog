"""LangGraph state schema for the research agent."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


class ResearchState(TypedDict):
    """Shared state flowing through the LangGraph research graph."""

    # The original user query
    query: str

    # Chat message history (accumulates via operator.add)
    messages: Annotated[list[BaseMessage], operator.add]

    # Raw search/scrape results collected so far (accumulates)
    search_results: Annotated[list[str], operator.add]

    # Structured candidate models discovered by the reflect node
    candidates: list[dict]

    # Gaps identified by the reflect node for the next search iteration
    gaps: list[str]

    # Whether the reflect node considers research complete
    research_complete: bool

    # Current search iteration counter
    iteration: int

    # Final Markdown recommendation report
    report: str
