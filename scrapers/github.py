"""Public GitHub page scraper."""

from __future__ import annotations

from urllib.parse import urlparse

from config import AtlasConfig
from .common import FetchOutcome, NetworkMonitor, fetch_html, parse_page_summary


class GitHubScraper:
    """Extract compact public context from GitHub URLs."""

    def can_handle(self, url: str) -> bool:
        """Return True when the URL belongs to GitHub."""

        return "github.com" in url.lower()

    def scrape(self, url: str, timeout: int, monitor: NetworkMonitor | None = None, config: AtlasConfig | None = None) -> FetchOutcome:
        """Return a compact summary of the public GitHub page."""

        parsed = urlparse(url)
        if not parsed.netloc:
            return FetchOutcome(url=url, available=False, reason="Invalid URL")
        fetched = fetch_html(url, timeout=timeout, monitor=monitor, config=config)
        if not fetched.available:
            return fetched
        page = parse_page_summary(url, fetched.text)
        summary = page.summarize(1500)
        return FetchOutcome(url=url, text=summary, available=True, elapsed_seconds=fetched.elapsed_seconds)
