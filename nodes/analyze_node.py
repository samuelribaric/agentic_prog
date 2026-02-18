"""Analyze node — reasoning agent that categorizes transactions and calculates totals."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from state import FinanceState
from models import get_reasoning_model, strip_think_tags
from prompts import ANALYZE_SYSTEM, ANALYZE_HUMAN


def analyze_node(state: FinanceState) -> dict:
    """Categorize transactions, calculate totals, and identify spending patterns."""
    llm = get_reasoning_model()

    transactions = state.get("transactions", [])

    # Format transactions for the LLM (cap at 500 to avoid context overflow)
    tx_lines = []
    for tx in transactions[:500]:
        tx_date = tx.get("date", "")
        desc = tx.get("description", "")
        amount = tx.get("amount", 0)
        currency = tx.get("currency", "SEK")
        tx_lines.append(f"- [{tx_date}] {desc}: {amount} {currency}")

    transactions_text = "\n".join(tx_lines) if tx_lines else "No transactions available."

    # Extract supervisor instructions
    notes = state.get("supervisor_notes", "")
    instructions = ""
    if "Instructions:" in notes:
        instructions = notes.split("Instructions:")[-1].strip()
    if not instructions:
        instructions = "Analyze all spending and provide a category breakdown."

    human_text = ANALYZE_HUMAN.format(
        query=state["query"],
        instructions=instructions,
        count=len(transactions),
        transactions=transactions_text,
    )

    messages = [
        SystemMessage(content=ANALYZE_SYSTEM),
        HumanMessage(content=human_text),
    ]

    response = llm.invoke(messages)
    analysis = strip_think_tags(response.content)

    return {
        "analysis": analysis,
        "messages": [HumanMessage(
            content=f"Analysis complete: {len(transactions)} transactions analyzed."
        )],
    }
