"""Portfolio website scraper."""

from __future__ import annotations

from urllib.parse import urlparse

from .common import fetch_html, parse_page_summary


class PortfolioScraper:
    """Extract compact public context from portfolio URLs."""

    def can_handle(self, url: str) -> bool:
        """Return True for any public website that is not a known social profile."""

        return url.startswith("http://") or url.startswith("https://")

    def scrape(self, url: str, timeout: int) -> str:
        """Return a compact summary of the public portfolio page."""

        parsed = urlparse(url)
        if not parsed.netloc:
            return ""
        html = fetch_html(url, timeout=timeout)
        page = parse_page_summary(url, html)
        return page.summarize(1800)
