"""Supervisor node — routes between data_fetch, analyze, advise, or done."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from state import FinanceState
from models import get_tool_model
from prompts import SUPERVISOR_SYSTEM, SUPERVISOR_HUMAN
import config


def supervisor_node(state: FinanceState) -> dict:
    """Decide which agent should run next based on current state."""
    turn = state.get("turn", 0)

    # Safety limit — stop if we've exceeded max turns
    if turn >= config.MAX_AGENT_TURNS:
        return {
            "next_agent": "done",
            "supervisor_notes": f"Reached max turns ({config.MAX_AGENT_TURNS}), stopping.",
            "turn": turn + 1,
        }

    llm = get_tool_model()  # llama3.1:8b at temp=0

    human_text = SUPERVISOR_HUMAN.format(
        query=state["query"],
        accounts_count=len(state.get("accounts", [])),
        transactions_count=len(state.get("transactions", [])),
        has_analysis="Yes" if state.get("analysis") else "No",
        turn=turn,
        max_turns=config.MAX_AGENT_TURNS,
        supervisor_notes=state.get("supervisor_notes", "None"),
    )

    messages = [
        SystemMessage(content=SUPERVISOR_SYSTEM),
        HumanMessage(content=human_text),
    ]

    # ── Deterministic routing based on state ────────────────────────────────
    # llama3.1:8b is unreliable at following routing rules, so we derive the
    # next agent from the state directly and only ask the LLM for instructions.
    has_transactions = bool(state.get("transactions"))
    has_analysis = bool(state.get("analysis"))

    if not has_transactions:
        next_agent = "data_fetch"
    elif not has_analysis:
        next_agent = "analyze"
    else:
        next_agent = "advise"

    # ── Ask LLM only for the instructions text ───────────────────────────────
    response = llm.invoke(messages)
    content = response.content.strip()

    instructions = ""
    try:
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            parsed = json.loads(content[json_start:json_end])
            instructions = parsed.get("instructions", parsed.get("reason", ""))
    except json.JSONDecodeError:
        pass

    notes = f"[Turn {turn}] → {next_agent}"
    if instructions:
        notes += f" | Instructions: {instructions}"

    return {
        "next_agent": next_agent,
        "supervisor_notes": notes,
        "turn": turn + 1,
    }
