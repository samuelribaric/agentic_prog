"""GitHub search tools — repos and issues via REST API."""

import requests
from langchain_core.tools import tool

import config

_API = "https://api.github.com"


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    return h


@tool
def github_search_repos(query: str, max_results: int = 5) -> str:
    """Search GitHub repositories. Returns repo name, description, stars, and URL."""
    try:
        resp = requests.get(
            f"{_API}/search/repositories",
            params={"q": query, "sort": "stars", "per_page": max_results},
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return f"No repos found for: {query}"
        formatted = []
        for r in items:
            formatted.append(
                f"Repo: {r['full_name']}\n"
                f"Stars: {r['stargazers_count']}\n"
                f"Description: {r.get('description', 'N/A')}\n"
                f"URL: {r['html_url']}\n"
            )
        return "\n---\n".join(formatted)
    except Exception as e:
        return f"GitHub repo search error: {e}"


@tool
def github_search_issues(query: str, max_results: int = 5) -> str:
    """Search GitHub issues and discussions. Returns title, body preview, and URL."""
    try:
        resp = requests.get(
            f"{_API}/search/issues",
            params={"q": query, "sort": "reactions", "per_page": max_results},
            headers=_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return f"No issues found for: {query}"
        formatted = []
        for issue in items:
            body = (issue.get("body") or "")[:300]
            formatted.append(
                f"Title: {issue['title']}\n"
                f"Repo: {issue.get('repository_url', 'N/A').split('/repos/')[-1]}\n"
                f"URL: {issue['html_url']}\n"
                f"Body: {body}\n"
            )
        return "\n---\n".join(formatted)
    except Exception as e:
        return f"GitHub issue search error: {e}"
