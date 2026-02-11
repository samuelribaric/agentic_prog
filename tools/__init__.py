"""Tool registry — exports all tools for use by the search node."""

from tools.search_tool import ddg_search
from tools.scraper_tool import scrape_url
from tools.github_tool import github_search_repos, github_search_issues

ALL_TOOLS = [ddg_search, scrape_url, github_search_repos, github_search_issues]

__all__ = [
    "ddg_search",
    "scrape_url",
    "github_search_repos",
    "github_search_issues",
    "ALL_TOOLS",
]
