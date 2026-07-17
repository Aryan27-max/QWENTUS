"""OCR helpers for image-based PDF resumes."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import fitz

from config import AtlasConfig


class OcrUnavailableError(RuntimeError):
    """Raised when the OCR backend is unavailable or fails to initialize."""


@dataclass(frozen=True)
class OcrResult:
    """Compact OCR output for a single PDF."""

    text: str
    used: bool
    reason: str = ""


class EasyOcrEngine:
    """Lazy EasyOCR wrapper that renders PDF pages into images."""

    def __init__(self, config: AtlasConfig) -> None:
        self.config = config
        self._reader: Any | None = None

    @property
    def reader(self):  # type: ignore[no-untyped-def]
        if self._reader is None:
            try:
                import easyocr
            except Exception as exc:  # pragma: no cover - dependency may be absent in some environments
                raise OcrUnavailableError("EasyOCR is not installed.") from exc

            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False, download_enabled=True)
        return self._reader

    def extract_text(self, pdf_path: Path) -> OcrResult:
        """Run OCR page-by-page and return the recovered text."""

        chunks: list[str] = []
        try:
            with fitz.open(pdf_path) as document:
                for page in document:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
                    image = self._pixmap_to_array(pixmap)
                    lines = self.reader.readtext(image, detail=0, paragraph=True)
                    recovered = " ".join(str(item).strip() for item in lines if str(item).strip())
                    if recovered:
                        chunks.append(recovered)
        except OcrUnavailableError:
            raise
        except Exception as exc:
            raise OcrUnavailableError(f"OCR failed for {pdf_path.name}") from exc

        text = "\n".join(chunks).strip()
        if not text:
            return OcrResult(text="", used=True, reason="OCR returned no readable text")
        return OcrResult(text=text, used=True)

    def _pixmap_to_array(self, pixmap):  # type: ignore[no-untyped-def]
        import numpy as np

        channels = pixmap.n
        if channels not in (3, 4):
            pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
            channels = pixmap.n
        array = np.frombuffer(pixmap.samples, dtype=np.uint8)
        return array.reshape(pixmap.height, pixmap.width, channels)


@lru_cache(maxsize=1)
def get_ocr_engine(config: AtlasConfig) -> EasyOcrEngine:
    """Return a cached OCR engine instance."""

    return EasyOcrEngine(config)
