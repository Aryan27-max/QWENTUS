"""Shared scraping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from bs4 import BeautifulSoup
import requests


DEFAULT_HEADERS: Final[dict[str, str]] = {
    "User-Agent": "AtlasResumeScreening/1.0 (+offline local analysis)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass(frozen=True)
class ScrapedPage:
    """Small summary returned by a website scraper."""

    url: str
    title: str = ""
    description: str = ""
    text: str = ""

    def summarize(self, limit: int) -> str:
        """Convert the page into compact context for the LLM prompt."""

        parts = [part for part in (self.title, self.description, self.text) if part]
        combined = " | ".join(parts)
        return combined[:limit]


def fetch_html(url: str, timeout: int) -> str:
    """Fetch HTML for a public URL."""

    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    return response.text


def parse_page_summary(url: str, html: str) -> ScrapedPage:
    """Reduce a page to the most useful public signals."""

    soup = BeautifulSoup(html, "html.parser")
    title = ""
    description = ""
    if soup.title and soup.title.string:
        title = " ".join(soup.title.string.split())
    meta = soup.find("meta", attrs={"name": "description"})
    if meta and meta.get("content"):
        description = " ".join(str(meta.get("content")).split())
    text = " ".join(soup.get_text(" ").split())
    return ScrapedPage(url=url, title=title, description=description, text=text)
