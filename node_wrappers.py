"""Wrapped node functions that emit events to the event bus.

These wrap the original node functions without modifying them. The web app
uses these instead of the originals so the UI can observe execution.
"""

from __future__ import annotations

import json
import traceback

from event_bus import Event, EventType, emit
from nodes import (
    supervisor_node as _original_supervisor,
    data_fetch_node as _original_data_fetch,
    analyze_node as _original_analyze,
    advise_node as _original_advise,
)


def _emit_start(node_name: str, state: dict) -> None:
    emit(Event(
        type=EventType.NODE_START,
        node=node_name,
        data={
            "turn": state.get("turn", 0),
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

def supervisor_node(state):
    """Wrapped supervisor node — emits routing decision."""
    _emit_start("supervisor", state)
    try:
        result = _original_supervisor(state)
        emit(Event(
            type=EventType.LLM_RESPONSE,
            node="supervisor",
            data={
                "next_agent": result.get("next_agent", ""),
                "notes": result.get("supervisor_notes", ""),
            },
        ))
        _emit_end("supervisor", {
            "next_agent": result.get("next_agent", ""),
            "turn": result.get("turn", 0),
        })
        return result
    except Exception as e:
        _emit_error("supervisor", e)
        raise


def data_fetch_node(state):
    """Wrapped data_fetch node — emits TOOL_RESULT for each tool output."""
    _emit_start("data_fetch", state)
    try:
        result = _original_data_fetch(state)
        accounts = result.get("accounts", [])
        transactions = result.get("transactions", [])
        emit(Event(
            type=EventType.TOOL_RESULT,
            node="data_fetch",
            data={
                "accounts_count": len(accounts),
                "transactions_count": len(transactions),
            },
        ))
        _emit_end("data_fetch", {
            "accounts_fetched": len(accounts),
            "transactions_fetched": len(transactions),
        })
        return result
    except Exception as e:
        _emit_error("data_fetch", e)
        raise


def analyze_node(state):
    """Wrapped analyze node — emits LLM_RESPONSE with analysis summary."""
    _emit_start("analyze", state)
    try:
        result = _original_analyze(state)
        analysis = result.get("analysis", "")
        emit(Event(
            type=EventType.LLM_RESPONSE,
            node="analyze",
            data={
                "analysis_preview": analysis[:500],
                "analysis_length": len(analysis),
            },
        ))
        _emit_end("analyze", {"analysis_length": len(analysis)})
        return result
    except Exception as e:
        _emit_error("analyze", e)
        raise


def advise_node(state):
    """Wrapped advise node — emits REPORT with full Markdown response."""
    _emit_start("advise", state)
    try:
        result = _original_advise(state)
        report = result.get("report", "")
        emit(Event(
            type=EventType.REPORT,
            node="advise",
            data={"report": report},
        ))
        _emit_end("advise", {"report_length": len(report)})
        return result
    except Exception as e:
        _emit_error("advise", e)
        raise
