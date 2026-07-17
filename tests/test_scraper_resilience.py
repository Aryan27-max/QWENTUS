"""Resilience tests for scraper failures and retry handling."""

from __future__ import annotations

import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import requests

from agents.evaluator import CandidateEvaluator
from config import AtlasConfig, AtlasPaths
from llm.ollama import OllamaClient
from scrapers.common import fetch_html, has_internet_connectivity
from scrapers.github import GitHubScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.portfolio import PortfolioScraper


def _mock_response(text: str, status_error: Exception | None = None):
    response = MagicMock()
    response.text = text
    response.raise_for_status.side_effect = status_error
    return response


class ScraperResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._sleep_patch = patch("scrapers.common.time.sleep", return_value=None)
        self._sleep_patch.start()

    def tearDown(self) -> None:
        self._sleep_patch.stop()

    def test_successful_scrape(self) -> None:
        html = "<html><title>Jane</title><meta name='description' content='Engineer'></html>"
        with patch("scrapers.common.requests.get", return_value=_mock_response(html)):
            outcome = fetch_html("https://github.com/janedoe", timeout=1)
        self.assertTrue(outcome.available)
        self.assertIn("Jane", outcome.text)

    def test_broken_github_url_returns_unavailable(self) -> None:
        response = _mock_response("", status_error=requests.HTTPError("404 Not Found"))
        with patch("scrapers.common.requests.get", return_value=response):
            outcome = GitHubScraper().scrape("https://github.com/janedoe", timeout=1)
        self.assertFalse(outcome.available)
        self.assertEqual(outcome.text, "")

    def test_deleted_github_account_returns_unavailable(self) -> None:
        response = _mock_response("", status_error=requests.HTTPError("404 Not Found"))
        with patch("scrapers.common.requests.get", return_value=response):
            outcome = GitHubScraper().scrape("https://github.com/missing-account", timeout=1)
        self.assertFalse(outcome.available)

    def test_invalid_url_returns_unavailable(self) -> None:
        outcome = GitHubScraper().scrape("not-a-valid-url", timeout=1)
        self.assertFalse(outcome.available)
        self.assertEqual(outcome.reason, "Invalid URL")

    def test_ssl_failure_returns_unavailable(self) -> None:
        with patch("scrapers.common.requests.get", side_effect=ssl.SSLError("SSL handshake failed")):
            outcome = GitHubScraper().scrape("https://github.com/janedoe", timeout=1)
        self.assertFalse(outcome.available)
        self.assertIn("SSL", outcome.reason)

    def test_timeout_returns_unavailable(self) -> None:
        with patch("scrapers.common.requests.get", side_effect=requests.Timeout("Timed out after 10 seconds")):
            outcome = GitHubScraper().scrape("https://github.com/janedoe", timeout=1)
        self.assertFalse(outcome.available)
        self.assertIn("Timed out", outcome.reason)

    def test_connection_reset_returns_unavailable(self) -> None:
        with patch("scrapers.common.requests.get", side_effect=ConnectionResetError("Connection reset by peer")):
            outcome = GitHubScraper().scrape("https://github.com/janedoe", timeout=1)
        self.assertFalse(outcome.available)
        self.assertIn("Connection reset", outcome.reason)

    def test_invalid_github_account_http_error_is_handled(self) -> None:
        response = _mock_response("", status_error=requests.HTTPError("404 Not Found"))
        with patch("scrapers.common.requests.get", return_value=response):
            outcome = fetch_html("https://github.com/missing-account", timeout=1)
        self.assertFalse(outcome.available)
        self.assertIn("404", outcome.reason)

    def test_linkedin_unavailable_is_handled(self) -> None:
        with patch("scrapers.common.requests.get", side_effect=requests.ConnectionError("LinkedIn blocked request")):
            outcome = LinkedInScraper().scrape("https://linkedin.com/in/janedoe", timeout=1)
        self.assertFalse(outcome.available)

    def test_portfolio_unavailable_is_handled(self) -> None:
        with patch("scrapers.common.requests.get", side_effect=requests.RequestException("Portfolio offline")):
            outcome = PortfolioScraper().scrape("https://portfolio.example.com", timeout=1)
        self.assertFalse(outcome.available)

    def test_internet_disconnected_skips_scraping(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            paths = AtlasPaths(
                root=temp_root,
                workspace=temp_root / "workspace",
                incoming=temp_root / "workspace" / "Incoming",
                processing=temp_root / "workspace" / "Processing",
                shortlisted=temp_root / "workspace" / "Shortlisted",
                maybe=temp_root / "workspace" / "Maybe",
                rejected=temp_root / "workspace" / "Rejected",
                failed=temp_root / "workspace" / "Failed",
                reports=temp_root / "workspace" / "Reports",
                logs=temp_root / "logs",
                docs=temp_root / "docs",
            )
            config = AtlasConfig(paths=paths)
            config.ensure_directories()
            pdf_path = paths.incoming / "resume.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "Jane Doe\nhttps://github.com/janedoe\nhttps://linkedin.com/in/janedoe")
            document.save(pdf_path)
            document.close()

            client = OllamaClient(config)
            evaluator = CandidateEvaluator(config, client, logger=MagicMock(), internet_available=False)

            with patch("scrapers.common.requests.get") as mock_get:
                profile = evaluator.build_profile(pdf_path)
            self.assertFalse(mock_get.called)
            self.assertEqual(profile.source_summaries["github"], "Unavailable")
            self.assertEqual(profile.source_summaries["linkedin"], "Unavailable")

    def test_has_internet_connectivity_false(self) -> None:
        with patch("scrapers.common.socket.create_connection", side_effect=OSError("network unreachable")):
            self.assertFalse(has_internet_connectivity())


if __name__ == "__main__":
    unittest.main()
