"""Excel exporter tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from config import AtlasConfig, AtlasPaths
from exporters.excel import ExcelExporter
from models.candidate import ScreeningRecord


class ExcelExporterTests(unittest.TestCase):
    def test_export_creates_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            config = AtlasConfig(paths=AtlasPaths(root=temp_root, workspace=temp_root / "workspace", incoming=temp_root / "workspace" / "Incoming", processing=temp_root / "workspace" / "Processing", shortlisted=temp_root / "workspace" / "Shortlisted", maybe=temp_root / "workspace" / "Maybe", rejected=temp_root / "workspace" / "Rejected", reports=temp_root / "workspace" / "Reports", logs=temp_root / "logs", docs=temp_root / "docs"))
            config.ensure_directories()
            exporter = ExcelExporter(config)
            report = exporter.export([
                ScreeningRecord(candidate_name="Jane", overall_score=80, technical_score=90, github_score=70, projects_score=85, leadership_score=60, communication_score=75, achievements_score=65, recommendation="Shortlisted", decision="Shortlisted", summary="Strong candidate"),
            ])
            self.assertTrue(report.exists())


if __name__ == "__main__":
    unittest.main()
