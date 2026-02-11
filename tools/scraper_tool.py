"""URL scraper tool — fetches a page and converts to clean text."""

import requests
from bs4 import BeautifulSoup
import html2text
from langchain_core.tools import tool


@tool
def scrape_url(url: str) -> str:
    """Fetch a URL and return its main text content (max 4000 chars)."""
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "ResearchBot/1.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.body_width = 0
        text = converter.handle(str(soup))

        # Truncate to keep context windows manageable
        if len(text) > 4000:
            text = text[:4000] + "\n\n[...truncated]"
        return text
    except Exception as e:
        return f"Scrape error for {url}: {e}"
