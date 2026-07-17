"""URL extraction helpers."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_URL_PATTERN = re.compile(r"https?://[^\s<>()\[\]{}\"']+", re.IGNORECASE)


class LinkExtractor:
    """Extract and normalize URLs from resume text."""

    def extract(self, text: str) -> list[str]:
        """Find URLs in plain text while preserving ordering."""

        seen: set[str] = set()
        links: list[str] = []
        for match in _URL_PATTERN.findall(text):
            normalized = self._normalize(match)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            links.append(normalized)
        return links

    def _normalize(self, url: str) -> str:
        url = url.rstrip(".,);]")
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ""
        return url
