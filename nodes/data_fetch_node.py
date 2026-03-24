"""Data fetch node — tool-calling agent that retrieves bank account and transaction data."""

from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from state import FinanceState
from models import get_tool_model
from prompts import DATA_FETCH_SYSTEM, DATA_FETCH_HUMAN
from tools import FINANCE_TOOLS

_tool_map = {t.name: t for t in FINANCE_TOOLS}


def _extract_period(instructions: str) -> str:
    """Infer the desired time period from supervisor instructions."""
    instr = instructions.lower()
    if "year" in instr:
        return "year"
    if "6 month" in instr or "6month" in instr or "half year" in instr:
        return "6months"
    if "3 month" in instr or "3month" in instr or "quarter" in instr:
        return "3months"
    if "week" in instr:
        return "week"
    return "month"  # default


def data_fetch_node(state: FinanceState) -> dict:
    """Fetch bank data using tool calls. Parses JSON results into state lists."""
    llm = get_tool_model().bind_tools(FINANCE_TOOLS)

    # Extract supervisor instructions from notes
    notes = state.get("supervisor_notes", "")
    instructions = ""
    if "Instructions:" in notes:
        instructions = notes.split("Instructions:")[-1].strip()
    if not instructions:
        instructions = "Fetch all accounts and their transactions for the current month."

    human_text = DATA_FETCH_HUMAN.format(
        instructions=instructions,
        query=state["query"],
    )

    messages = [
        SystemMessage(content=DATA_FETCH_SYSTEM),
        HumanMessage(content=human_text),
    ]

    new_accounts: list[dict] = []
    new_transactions: list[dict] = []
    # Track (tool_name, result_str) pairs for structured parsing
    tool_call_results: list[tuple[str, str]] = []
    # Track LLM text replies when no tool calls are made (for diagnostics)
    no_tool_responses: list[str] = []

    # Allow up to 6 rounds of tool calling per invocation
    for round_num in range(6):
        response = llm.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            no_tool_responses.append(response.content[:300] if response.content else "<empty>")
            # On first round, re-prompt once to force a tool call
            if round_num == 0:
                messages.append(HumanMessage(
                    content="You MUST call a tool now. Start by calling list_accounts. "
                            "Do not explain — just call the tool."
                ))
                continue
            break

        for tc in response.tool_calls:
            tool_fn = _tool_map.get(tc["name"])
            if tool_fn is None:
                result = json.dumps({"error": f"Unknown tool: {tc['name']}"})
            else:
                try:
                    args = dict(tc["args"])
                    # Normalize 'q' → 'query' for search_web
                    if "q" in args and "query" not in args:
                        args["query"] = args.pop("q")
                    result = tool_fn.invoke(args)
                except Exception as e:
                    result = json.dumps({"error": f"Tool error ({tc['name']}): {e}"})

            result_str = str(result)
            tool_call_results.append((tc["name"], result_str))
            messages.append(ToolMessage(content=result_str, tool_call_id=tc["id"]))

    # Parse structured data out of tool results
    for tool_name, result_str in tool_call_results:
        if tool_name == "list_accounts":
            try:
                parsed = json.loads(result_str)
                if isinstance(parsed, list):
                    new_accounts = parsed
            except (json.JSONDecodeError, TypeError):
                pass

        elif tool_name == "get_transactions":
            try:
                parsed = json.loads(result_str)
                if isinstance(parsed, list):
                    new_transactions.extend(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    # Fallback: if we have accounts but the LLM failed to call get_transactions
    # (it wrote the call as text instead of invoking it), do it directly.
    if new_accounts and not new_transactions:
        period = _extract_period(instructions)
        get_tx = _tool_map.get("get_transactions")
        if get_tx:
            for acct in new_accounts:
                acct_id = acct.get("id", "")
                if not acct_id:
                    continue
                try:
                    result_str = str(get_tx.invoke({"account_id": acct_id, "period": period}))
                except Exception as e:
                    result_str = json.dumps({"error": f"Tool error (get_transactions): {e}"})
                tool_call_results.append(("get_transactions", result_str))
                try:
                    parsed = json.loads(result_str)
                    if isinstance(parsed, list):
                        new_transactions.extend(parsed)
                except (json.JSONDecodeError, TypeError):
                    pass

    # Collect any error messages from tool results for diagnostics
    tool_errors = [
        f"{name}: {result_str}"
        for name, result_str in tool_call_results
        if '"error"' in result_str
    ]

    status_msg = (
        f"Data fetch complete: {len(new_accounts)} accounts, "
        f"{len(new_transactions)} transactions fetched."
    )
    if tool_errors:
        status_msg += " Errors: " + " | ".join(tool_errors)

    update: dict = {
        "messages": [HumanMessage(content=status_msg)],
        # Extra key for the wrapper to read — ignored by LangGraph state
        "_tool_outputs": tool_call_results,
        "_no_tool_responses": no_tool_responses,
    }

    if new_accounts:
        update["accounts"] = new_accounts
    if new_transactions:
        update["transactions"] = new_transactions

    return update
