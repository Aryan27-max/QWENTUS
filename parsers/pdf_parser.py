"""PDF text extraction helpers."""

from __future__ import annotations

from pathlib import Path
import time

import fitz

from config import AtlasConfig, DEFAULT_CONFIG
from parsers.ocr import OcrResult, get_ocr_engine, OcrUnavailableError


class PDFParseError(RuntimeError):
    """Raised when a PDF cannot be parsed."""


class PDFExtractionResult:
    """Text extraction result and timing data for a resume PDF."""

    def __init__(self, text: str, pdf_time: float, ocr_time: float, ocr_used: bool, ocr_reason: str = "") -> None:
        self.text = text
        self.pdf_time = pdf_time
        self.ocr_time = ocr_time
        self.ocr_used = ocr_used
        self.ocr_reason = ocr_reason

    def __str__(self) -> str:
        return self.text

    def __contains__(self, item: object) -> bool:
        return str(item) in self.text

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return getattr(self.text, name)


class PDFParser:
    """Extract text from PDF resumes."""

    def __init__(self, config: AtlasConfig | None = None) -> None:
        self.config = config or DEFAULT_CONFIG

    def extract_text(self, pdf_path: Path) -> PDFExtractionResult:
        """Return the combined text for all pages in a PDF, with OCR fallback."""

        chunks: list[str] = []
        document = None
        pdf_started = time.perf_counter()
        try:
            pdf_bytes = pdf_path.read_bytes()
            document = fitz.open(stream=pdf_bytes, filetype="pdf")
            for page in document:
                page_text = page.get_text("text")
                if page_text:
                    chunks.append(page_text)
        except Exception as exc:
            raise PDFParseError(f"Unable to parse PDF: {pdf_path.name}") from exc
        finally:
            if document is not None:
                document.close()
        pdf_time = time.perf_counter() - pdf_started
        text = "\n".join(chunks).strip()
        if text:
            return PDFExtractionResult(text=text, pdf_time=pdf_time, ocr_time=0.0, ocr_used=False)

        ocr_started = time.perf_counter()
        try:
            ocr_engine = get_ocr_engine(self.config)
            ocr_result = ocr_engine.extract_text(pdf_path)
        except OcrUnavailableError as exc:
            raise PDFParseError(f"OCR failed for {pdf_path.name}") from exc
        ocr_time = time.perf_counter() - ocr_started
        if not ocr_result.text:
            raise PDFParseError(f"No readable text found in PDF: {pdf_path.name}")
        return PDFExtractionResult(text=ocr_result.text, pdf_time=pdf_time, ocr_time=ocr_time, ocr_used=True, ocr_reason=ocr_result.reason)
