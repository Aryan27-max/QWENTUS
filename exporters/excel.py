"""Excel report generation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from statistics import mean

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from config import AtlasConfig
from models.candidate import ScreeningRecord


class ExcelExporter:
    """Create recruiter-friendly Excel workbooks."""

    def __init__(self, config: AtlasConfig) -> None:
        self.config = config

    def export(self, records: list[ScreeningRecord]) -> Path:
        """Write the screening report workbook to the Reports directory."""

        self.config.ensure_directories()
        workbook = Workbook()
        summary_sheet = workbook.active
        summary_sheet.title = "Summary"
        detail_sheet = workbook.create_sheet("Candidates")

        self._write_candidates(detail_sheet, records)
        self._write_summary(summary_sheet, records)

        report_path = self.config.paths.reports / "atlas_screening_report.xlsx"
        workbook.save(report_path)
        return report_path

    def _write_candidates(self, sheet, records: list[ScreeningRecord]) -> None:
        headers = [
            "Rank",
            "Candidate Name",
            "Email",
            "Phone",
            "College",
            "Degree",
            "Overall Score",
            "Technical Score",
            "GitHub Score",
            "Projects Score",
            "Leadership",
            "Communication",
            "Achievements",
            "Strengths",
            "Weaknesses",
            "Recommendation",
            "Decision",
            "Summary",
            "Resume File",
            "GitHub URL",
            "LinkedIn URL",
            "Portfolio URL",
        ]
        header_fill = PatternFill(fill_type="solid", fgColor="1F2937")
        header_font = Font(color="FFFFFF", bold=True)
        for column_index, header in enumerate(headers, start=1):
            cell = sheet.cell(row=1, column=column_index, value=header)
            cell.fill = header_fill
            cell.font = header_font

        for row_index, record in enumerate(records, start=2):
            values = [
                record.rank,
                record.candidate_name,
                record.email,
                record.phone,
                record.college,
                record.degree,
                record.overall_score,
                record.technical_score,
                record.github_score,
                record.projects_score,
                record.leadership_score,
                record.communication_score,
                record.achievements_score,
                record.strengths,
                record.weaknesses,
                record.recommendation,
                record.decision,
                record.summary,
                record.resume_file,
                record.github_url,
                record.linkedin_url,
                record.portfolio_url,
            ]
            for column_index, value in enumerate(values, start=1):
                sheet.cell(row=row_index, column=column_index, value=value)

        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        self._autosize_columns(sheet)

    def _write_summary(self, sheet, records: list[ScreeningRecord]) -> None:
        total = len(records)
        scores = [record.overall_score for record in records]
        recommendations = Counter(record.recommendation for record in records)

        rows = [
            ("Total Candidates", total),
            ("Shortlisted", recommendations.get("Shortlisted", 0)),
            ("Maybe", recommendations.get("Maybe", 0)),
            ("Rejected", recommendations.get("Rejected", 0)),
            ("Average Overall Score", round(mean(scores), 2) if scores else 0),
            ("Highest Score", max(scores) if scores else 0),
            ("Lowest Score", min(scores) if scores else 0),
        ]
        for row_index, (label, value) in enumerate(rows, start=1):
            sheet.cell(row=row_index, column=1, value=label)
            sheet.cell(row=row_index, column=2, value=value)

        sheet.cell(row=10, column=1, value="Recommendation Distribution")
        for offset, (label, count) in enumerate(sorted(recommendations.items()), start=11):
            sheet.cell(row=offset, column=1, value=label)
            sheet.cell(row=offset, column=2, value=count)

        sheet.cell(row=15, column=1, value="Top Candidates")
        top_candidates = sorted(records, key=lambda item: item.overall_score, reverse=True)[:10]
        for offset, record in enumerate(top_candidates, start=16):
            sheet.cell(row=offset, column=1, value=record.rank)
            sheet.cell(row=offset, column=2, value=record.candidate_name)
            sheet.cell(row=offset, column=3, value=record.overall_score)

        sheet.column_dimensions["A"].width = 28
        sheet.column_dimensions["B"].width = 18
        sheet.column_dimensions["C"].width = 18

    def _autosize_columns(self, sheet) -> None:
        for column_cells in sheet.columns:
            values = [len(str(cell.value)) for cell in column_cells if cell.value is not None]
            width = min(max(values, default=10) + 2, 45)
            sheet.column_dimensions[get_column_letter(column_cells[0].column)].width = width
