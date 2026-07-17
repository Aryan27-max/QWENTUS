"""Parser and extractor tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import fitz

from parsers.link_extractor import LinkExtractor
from parsers.pdf_parser import PDFParser


class ParserTests(unittest.TestCase):
    def test_pdf_text_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = Path(temp_dir) / "resume.pdf"
            document = fitz.open()
            page = document.new_page()
            page.insert_text((72, 72), "Jane Doe\nEmail: jane@example.com\nGitHub: https://github.com/janedoe")
            document.save(pdf_path)
            document.close()

            text = PDFParser().extract_text(pdf_path)
            self.assertIn("Jane Doe", text)
            self.assertIn("jane@example.com", text)

    def test_link_extraction(self) -> None:
        text = "Visit https://github.com/janedoe and https://portfolio.example.com."
        links = LinkExtractor().extract(text)
        self.assertEqual(links, ["https://github.com/janedoe", "https://portfolio.example.com"])


if __name__ == "__main__":
    unittest.main()
