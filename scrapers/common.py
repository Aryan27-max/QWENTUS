"""Shared scraping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
import ipaddress
import socket
import ssl
import time
import threading
from typing import Final
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests
from requests import RequestException
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from config import AtlasConfig


DEFAULT_HEADERS: Final[dict[str, str]] = {
    "User-Agent": "AtlasResumeScreening/1.0 (+offline local analysis)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_DNS_LOCK = threading.Lock()


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


@dataclass(frozen=True)
class FetchOutcome:
    """Result of a web fetch with availability metadata."""

    url: str
    text: str = ""
    available: bool = False
    reason: str = ""
    elapsed_seconds: float = 0.0

    def as_summary(self, limit: int) -> str:
        """Return a truncated summary of fetched content."""

        return self.text[:limit]


@dataclass
class NetworkMonitor:
    """Track repeated network failures and temporarily disable scraping."""

    config: AtlasConfig
    consecutive_failures: int = 0
    disabled_until: float = 0.0
    warning_emitted: bool = False

    def is_disabled(self) -> bool:
        now = time.time()
        if self.disabled_until and now >= self.disabled_until:
            if has_internet_connectivity():
                self.consecutive_failures = 0
                self.disabled_until = 0.0
                self.warning_emitted = False
                return False
            self.disabled_until = now + self.config.network_recovery_seconds
        return self.disabled_until > now

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.warning_emitted = False

    def record_failure(self) -> bool:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.config.network_failure_threshold:
            self.disabled_until = time.time() + self.config.network_recovery_seconds
            self.consecutive_failures = 0
            self.warning_emitted = False
            return True
        return False


def has_internet_connectivity(timeout: float = 1.0) -> bool:
    """Perform a lightweight connectivity probe once per run."""

    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except Exception:
        return False


def _is_ip_address(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


@contextmanager
def _dns_resolution_override(resolvers: tuple[str, ...] | None):
    if not resolvers:
        yield
        return

    try:
        import dns.resolver
    except Exception:
        yield
        return

    with _DNS_LOCK:
        original_getaddrinfo = socket.getaddrinfo

        def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # type: ignore[no-untyped-def]
            if not host or _is_ip_address(str(host)):
                return original_getaddrinfo(host, port, family, type, proto, flags)

            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = list(resolvers)
            resolver.lifetime = 2.0
            resolver.timeout = 1.0

            addresses: list[str] = []
            for record_type in ("A", "AAAA"):
                try:
                    answers = resolver.resolve(str(host), record_type)
                except Exception:
                    continue
                for answer in answers:
                    value = str(answer).strip()
                    if value and value not in addresses:
                        addresses.append(value)

            if not addresses:
                return original_getaddrinfo(host, port, family, type, proto, flags)

            results = []
            for address in addresses:
                results.extend(original_getaddrinfo(address, port, family, type, proto, flags))
            return results

        socket.getaddrinfo = getaddrinfo
        try:
            yield
        finally:
            socket.getaddrinfo = original_getaddrinfo


def _format_failure_reason(exc: Exception) -> str:
    message = str(exc).strip()
    current: Exception | None = exc
    while current is not None:
        if isinstance(current, socket.gaierror):
            return "DNS resolution failed. Continuing without external profile."
        current = current.__cause__ if isinstance(current.__cause__, Exception) else None
    lowered = message.lower()
    if any(token in lowered for token in ("name or service not known", "temporary failure in name resolution", "dns", "getaddrinfo failed")):
        return "DNS resolution failed. Continuing without external profile."
    return message


def compact_url_summary(url: str) -> str:
    """Generate a tiny source hint from a URL without shipping raw HTML to the model."""

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    if "github.com" in host:
        return f"GitHub summary: {path or parsed.netloc}"
    if "linkedin.com" in host:
        return f"LinkedIn summary: {path or parsed.netloc}"
    return f"Portfolio summary: {host}/{path}".rstrip("/")


def fetch_html(url: str, timeout: int, retries: int = 3, monitor: NetworkMonitor | None = None, config: AtlasConfig | None = None) -> FetchOutcome:
    """Fetch HTML for a public URL with lightweight retry handling.

    On failure the caller receives an unavailable result rather than an exception.
    """

    delays = [0, 1, 2]
    last_reason = ""
    if monitor and monitor.is_disabled():
        return FetchOutcome(url=url, available=False, reason="Internet unavailable. Skipping GitHub, LinkedIn and Portfolio.")
    for attempt in range(min(retries, len(delays))):
        if attempt:
            time.sleep(delays[attempt])
        try:
            started = time.perf_counter()
            with _dns_resolution_override(config.dns_resolvers if config else None):
                response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            if monitor:
                monitor.record_success()
            return FetchOutcome(url=url, text=response.text, available=True, elapsed_seconds=time.perf_counter() - started)
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError, RequestException, Urllib3HTTPError, ssl.SSLError, socket.timeout, ConnectionResetError, OSError) as exc:
            last_reason = _format_failure_reason(exc)
            if monitor and monitor.record_failure() and not monitor.warning_emitted:
                monitor.warning_emitted = True
                last_reason = "Internet unavailable. Skipping GitHub, LinkedIn and Portfolio."
        except Exception as exc:  # pragma: no cover - defensive catch for runtime surprises
            last_reason = _format_failure_reason(exc)
        continue
    return FetchOutcome(url=url, available=False, reason=last_reason)


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
