"""PDF text extraction helpers."""

from __future__ import annotations

from pathlib import Path

import fitz


class PDFParser:
    """Extract text from PDF resumes."""

    def extract_text(self, pdf_path: Path) -> str:
        """Return the combined text for all pages in a PDF."""

        chunks: list[str] = []
        with fitz.open(pdf_path) as document:
            for page in document:
                page_text = page.get_text("text")
                if page_text:
                    chunks.append(page_text)
        return "\n".join(chunks)
