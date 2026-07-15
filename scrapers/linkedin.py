"""Public LinkedIn page scraper."""

from __future__ import annotations

from urllib.parse import urlparse

from .common import fetch_html, parse_page_summary


class LinkedInScraper:
    """Extract compact public context from LinkedIn URLs."""

    def can_handle(self, url: str) -> bool:
        """Return True when the URL belongs to LinkedIn."""

        return "linkedin.com" in url.lower()

    def scrape(self, url: str, timeout: int) -> str:
        """Return a compact summary of the public LinkedIn page."""

        parsed = urlparse(url)
        if not parsed.netloc:
            return ""
        html = fetch_html(url, timeout=timeout)
        page = parse_page_summary(url, html)
        return page.summarize(1500)
