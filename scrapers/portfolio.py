"""Portfolio website scraper."""

from __future__ import annotations

from urllib.parse import urlparse

from config import AtlasConfig
from .common import FetchOutcome, NetworkMonitor, fetch_html, parse_page_summary


class PortfolioScraper:
    """Extract compact public context from portfolio URLs."""

    def can_handle(self, url: str) -> bool:
        """Return True for any public website that is not a known social profile."""

        return url.startswith("http://") or url.startswith("https://")

    def scrape(self, url: str, timeout: int, monitor: NetworkMonitor | None = None, config: AtlasConfig | None = None) -> FetchOutcome:
        """Return a compact summary of the public portfolio page."""

        parsed = urlparse(url)
        if not parsed.netloc:
            return FetchOutcome(url=url, available=False, reason="Invalid URL")
        fetched = fetch_html(url, timeout=timeout, monitor=monitor, config=config)
        if not fetched.available:
            return fetched
        page = parse_page_summary(url, fetched.text)
        return FetchOutcome(url=url, text=page.summarize(1800), available=True, elapsed_seconds=fetched.elapsed_seconds)
