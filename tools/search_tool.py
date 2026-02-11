"""DuckDuckGo web search tool."""

from langchain_core.tools import tool
from duckduckgo_search import DDGS


@tool
def ddg_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo. Returns titles, URLs, and snippets."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return f"No results found for: {query}"
        formatted = []
        for r in results:
            formatted.append(
                f"Title: {r['title']}\nURL: {r['href']}\nSnippet: {r['body']}\n"
            )
        return "\n---\n".join(formatted)
    except Exception as e:
        return f"Search error: {e}"
