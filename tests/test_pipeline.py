"""Pipeline tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

import fitz

from config import AtlasConfig, AtlasPaths
from core.pipeline import AtlasPipeline
from llm.ollama import OllamaClient


class PipelineTests(unittest.TestCase):
    def test_pipeline_moves_pdf_and_creates_report(self) -> None:
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
                reports=temp_root / "workspace" / "Reports",
                logs=temp_root / "logs",
                docs=temp_root / "docs",
            )
            config = AtlasConfig(paths=paths, preprocess_workers=1)
            config.ensure_directories()

            pdf_path = paths.incoming / "candidate.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "Jane Doe\njane@example.com\nhttps://github.com/janedoe\nPython projects")
            document.save(pdf_path)
            document.close()

            client = OllamaClient(config)
            client.ensure_ready = MagicMock(return_value=None)
            client.evaluate_json = MagicMock(
                return_value={
                    "name": "Jane Doe",
                    "email": "jane@example.com",
                    "overall_score": 82,
                    "technical_score": 88,
                    "github_score": 80,
                    "projects_score": 86,
                    "leadership_score": 58,
                    "communication_score": 74,
                    "achievements_score": 69,
                    "recommendation": "Shortlisted",
                    "summary": "Strong candidate",
                    "strengths": ["Python"],
                    "weaknesses": ["Leadership depth"],
                }
            )
            with unittest.mock.patch("core.pipeline.has_internet_connectivity", return_value=True), unittest.mock.patch(
                "scrapers.common.requests.get",
                return_value=MagicMock(text="<html><title>Jane Doe</title></html>", raise_for_status=MagicMock(return_value=None)),
            ):
                pipeline = AtlasPipeline(config=config, ollama=client, logger=MagicMock())
                summary = pipeline.run_once()
            self.assertEqual(summary.processed, 1)
            self.assertTrue((paths.shortlisted / "candidate.pdf").exists())
            self.assertTrue(Path(summary.report_file).exists())


if __name__ == "__main__":
    unittest.main()
