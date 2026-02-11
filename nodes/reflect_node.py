"""Reflect node — uses deepseek-r1:8b to analyze findings and identify gaps."""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from state import ResearchState
from models import get_reasoning_model, strip_think_tags
from prompts import REFLECT_SYSTEM, REFLECT_HUMAN
import config


def reflect_node(state: ResearchState) -> dict:
    """Analyze search results, extract candidates, and decide if more research is needed."""
    llm = get_reasoning_model()

    search_text = "\n\n---\n\n".join(state.get("search_results", []))
    if len(search_text) > 8000:
        search_text = search_text[:8000] + "\n\n[...truncated]"

    candidates_text = json.dumps(state.get("candidates", []), indent=2)

    human_text = REFLECT_HUMAN.format(
        query=state["query"],
        iteration=state.get("iteration", 1),
        max_iterations=config.MAX_SEARCH_ITERATIONS,
        search_results=search_text,
        candidates=candidates_text,
    )

    messages = [
        SystemMessage(content=REFLECT_SYSTEM),
        HumanMessage(content=human_text),
    ]

    response = llm.invoke(messages)
    cleaned = strip_think_tags(response.content)

    # Parse JSON from the response
    try:
        # Try to find JSON in the response (it might be wrapped in markdown)
        json_start = cleaned.find("{")
        json_end = cleaned.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(cleaned[json_start:json_end])
        else:
            parsed = {}
    except json.JSONDecodeError:
        parsed = {}

    new_candidates = parsed.get("candidates", state.get("candidates", []))
    gaps = parsed.get("gaps", [])
    research_complete = parsed.get("research_complete", False)

    # Force completion if at max iterations
    if state.get("iteration", 1) >= config.MAX_SEARCH_ITERATIONS:
        research_complete = True

    return {
        "candidates": new_candidates,
        "gaps": gaps,
        "research_complete": research_complete,
        "messages": [HumanMessage(content=f"Reflection complete. Candidates: {len(new_candidates)}, Gaps: {len(gaps)}, Complete: {research_complete}")],
    }
