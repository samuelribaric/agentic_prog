"""Wrapped node functions that emit events to the event bus.

These wrap the original node functions without modifying them. The web app
uses these instead of the originals so the UI can observe execution.
"""

from __future__ import annotations

import json
import traceback

from event_bus import Event, EventType, emit
from nodes import (
    search_node as _original_search,
    reflect_node as _original_reflect,
    retrieve_node as _original_retrieve,
    finalize_node as _original_finalize,
)


def _emit_start(node_name: str, state: dict) -> None:
    emit(Event(
        type=EventType.NODE_START,
        node=node_name,
        data={
            "iteration": state.get("iteration", 0),
            "query": state.get("query", ""),
        },
    ))


def _emit_end(node_name: str, summary: dict) -> None:
    emit(Event(
        type=EventType.NODE_END,
        node=node_name,
        data=summary,
    ))


def _emit_error(node_name: str, error: Exception) -> None:
    emit(Event(
        type=EventType.ERROR,
        node=node_name,
        data={"error": str(error), "traceback": traceback.format_exc()},
    ))


# ---------------------------------------------------------------------------
# Wrapped nodes
# ---------------------------------------------------------------------------

def search_node(state):
    """Wrapped search node — emits TOOL_RESULT for each tool output."""
    _emit_start("search", state)
    try:
        result = _original_search(state)
        # Parse tool results: each item has format "[tool_name] content"
        for item in result.get("search_results", []):
            if item.startswith("[") and "]" in item:
                bracket_end = item.index("]")
                tool_name = item[1:bracket_end]
                content = item[bracket_end + 2:]  # skip "] "
            else:
                tool_name = "llm"
                content = item
            emit(Event(
                type=EventType.TOOL_RESULT,
                node="search",
                data={
                    "tool": tool_name,
                    "content": content[:1500],
                },
            ))
        _emit_end("search", {
            "results_count": len(result.get("search_results", [])),
            "iteration": result.get("iteration", 0),
        })
        return result
    except Exception as e:
        _emit_error("search", e)
        raise


def reflect_node(state):
    """Wrapped reflect node — emits LLM_RESPONSE with candidates/gaps."""
    _emit_start("reflect", state)
    try:
        result = _original_reflect(state)
        emit(Event(
            type=EventType.LLM_RESPONSE,
            node="reflect",
            data={
                "candidates": result.get("candidates", []),
                "gaps": result.get("gaps", []),
                "research_complete": result.get("research_complete", False),
            },
        ))
        _emit_end("reflect", {
            "candidates_count": len(result.get("candidates", [])),
            "gaps_count": len(result.get("gaps", [])),
            "research_complete": result.get("research_complete", False),
        })
        return result
    except Exception as e:
        _emit_error("reflect", e)
        raise


def retrieve_node(state):
    """Wrapped retrieve node — emits LLM_RESPONSE with retrieved texts."""
    _emit_start("retrieve", state)
    try:
        result = _original_retrieve(state)
        # Extract the ChromaDB text from search_results
        retrieved_texts = result.get("search_results", [])
        emit(Event(
            type=EventType.LLM_RESPONSE,
            node="retrieve",
            data={
                "retrieved": retrieved_texts,
            },
        ))
        _emit_end("retrieve", {
            "entries_count": len(retrieved_texts),
        })
        return result
    except Exception as e:
        _emit_error("retrieve", e)
        raise


def finalize_node(state):
    """Wrapped finalize node — emits REPORT with full markdown."""
    _emit_start("finalize", state)
    try:
        result = _original_finalize(state)
        report = result.get("report", "")
        emit(Event(
            type=EventType.REPORT,
            node="finalize",
            data={"report": report},
        ))
        _emit_end("finalize", {"report_length": len(report)})
        return result
    except Exception as e:
        _emit_error("finalize", e)
        raise
