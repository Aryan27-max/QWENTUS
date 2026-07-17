"""Pipeline resilience tests for fatal and non-fatal failures."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import requests

from config import AtlasConfig, AtlasPaths
from core.pipeline import AtlasPipeline
from llm.ollama import OllamaClient


def _make_pdf(path: Path, text: str) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    document.save(path)
    document.close()


class PipelineResilienceTests(unittest.TestCase):
    def test_pipeline_continues_after_scraper_failures_and_moves_only_fatal_pdfs_to_failed(self) -> None:
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
            config = AtlasConfig(paths=paths, preprocess_workers=1)
            config.ensure_directories()

            good_pdf = paths.incoming / "good.pdf"
            corrupt_pdf = paths.incoming / "corrupt.pdf"
            _make_pdf(good_pdf, "Jane Doe\njane@example.com\nhttps://github.com/janedoe\nhttps://linkedin.com/in/janedoe\nPortfolio: https://portfolio.example.com")
            corrupt_pdf.write_bytes(b"not a pdf")

            client = OllamaClient(config)
            client.ensure_ready = MagicMock(return_value=None)
            client.evaluate_json = MagicMock(
                return_value={
                    "name": "Jane Doe",
                    "email": "jane@example.com",
                    "overall_score": 82,
                    "technical_score": 88,
                    "github_score": 75,
                    "projects_score": 84,
                    "leadership_score": 60,
                    "communication_score": 72,
                    "achievements_score": 68,
                    "recommendation": "Shortlisted",
                    "summary": "Strong fit",
                    "strengths": ["Python"],
                    "weaknesses": ["Leadership depth"],
                }
            )

            def fake_get(url, *args, **kwargs):
                if "github.com" in url:
                    raise requests.ConnectionError("Connection reset by remote host")
                if "linkedin.com" in url:
                    raise requests.Timeout("Timed out after 10 seconds")
                if "portfolio.example.com" in url:
                    raise requests.RequestException("Portfolio offline")
                raise AssertionError(f"Unexpected URL: {url}")

            with patch("core.pipeline.has_internet_connectivity", return_value=True), patch(
                "scrapers.common.requests.get",
                side_effect=fake_get,
            ), patch("scrapers.common.time.sleep", return_value=None):
                pipeline = AtlasPipeline(config=config, ollama=client, logger=MagicMock())
                summary = pipeline.run_once()

            self.assertEqual(summary.processed, 1)
            self.assertEqual(summary.failed, 1)
            self.assertTrue((paths.shortlisted / "good.pdf").exists())
            self.assertTrue((paths.failed / "corrupt.pdf").exists())

    def test_pipeline_moves_resume_to_failed_after_repeated_llm_failure(self) -> None:
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
            config = AtlasConfig(paths=paths, preprocess_workers=1)
            config.ensure_directories()

            resume_pdf = paths.incoming / "llm-failure.pdf"
            _make_pdf(resume_pdf, "Jane Doe\njane@example.com\nPython projects")

            client = OllamaClient(config)
            client.ensure_ready = MagicMock(return_value=None)
            client.evaluate_json = MagicMock(side_effect=RuntimeError("Ollama unavailable"))

            with patch("core.pipeline.has_internet_connectivity", return_value=False), patch(
                "scrapers.common.time.sleep",
                return_value=None,
            ):
                pipeline = AtlasPipeline(config=config, ollama=client, logger=MagicMock())
                summary = pipeline.run_once()

            self.assertEqual(summary.processed, 0)
            self.assertEqual(summary.failed, 1)
            self.assertTrue((paths.failed / "llm-failure.pdf").exists())

    def test_pipeline_moves_resume_to_failed_after_repeated_json_validation_failure(self) -> None:
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
            config = AtlasConfig(paths=paths, preprocess_workers=1)
            config.ensure_directories()

            resume_pdf = paths.incoming / "json-validation-failure.pdf"
            _make_pdf(resume_pdf, "Jane Doe\njane@example.com\nPython projects")

            client = OllamaClient(config)
            client.ensure_ready = MagicMock(return_value=None)
            client.evaluate_json = MagicMock(return_value={"name": "Jane Doe", "email": "jane@example.com"})

            with patch("core.pipeline.has_internet_connectivity", return_value=False), patch(
                "scrapers.common.time.sleep",
                return_value=None,
            ):
                pipeline = AtlasPipeline(config=config, ollama=client, logger=MagicMock())
                summary = pipeline.run_once()

            self.assertEqual(summary.processed, 0)
            self.assertEqual(summary.failed, 1)
            self.assertTrue((paths.failed / "json-validation-failure.pdf").exists())


if __name__ == "__main__":
    unittest.main()
