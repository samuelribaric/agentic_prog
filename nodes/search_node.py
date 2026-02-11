"""Search node — uses llama3.1:8b to dispatch tool calls and gather research."""

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from state import ResearchState
from models import get_tool_model
from prompts import SEARCH_SYSTEM, SEARCH_HUMAN
from tools import ALL_TOOLS

# Build a name→tool mapping for execution
_tool_map = {t.name: t for t in ALL_TOOLS}


def search_node(state: ResearchState) -> dict:
    """Invoke the tool-calling LLM and execute any tool calls it makes."""
    llm = get_tool_model().bind_tools(ALL_TOOLS)

    gaps_section = ""
    if state.get("gaps"):
        gaps_section = "Information gaps to fill:\n" + "\n".join(
            f"- {g}" for g in state["gaps"]
        )

    human_text = SEARCH_HUMAN.format(query=state["query"], gaps_section=gaps_section)

    messages = [
        SystemMessage(content=SEARCH_SYSTEM),
        HumanMessage(content=human_text),
    ]

    collected_results: list[str] = []

    # Allow multiple rounds of tool calling (up to 6 calls per search node invocation)
    for _ in range(6):
        response = llm.invoke(messages)
        messages.append(response)

        if not response.tool_calls:
            # Model finished calling tools
            if response.content:
                collected_results.append(response.content)
            break

        # Execute each tool call
        for tc in response.tool_calls:
            tool_fn = _tool_map.get(tc["name"])
            if tool_fn is None:
                result = f"Unknown tool: {tc['name']}"
            else:
                try:
                    # Normalise args: LLMs sometimes use 'q' instead of 'query'
                    args = dict(tc["args"])
                    if "q" in args and "query" not in args:
                        args["query"] = args.pop("q")
                    result = tool_fn.invoke(args)
                except Exception as e:
                    result = f"Tool error ({tc['name']}): {e}"
            collected_results.append(f"[{tc['name']}] {result}")
            messages.append(
                ToolMessage(content=str(result), tool_call_id=tc["id"])
            )

    return {
        "search_results": collected_results,
        "messages": [HumanMessage(content=f"Search iteration completed with {len(collected_results)} results.")],
        "iteration": state.get("iteration", 0) + 1,
    }
