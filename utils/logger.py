"""Logging helpers for Atlas."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.logging import RichHandler


def configure_logging(log_dir: Path) -> logging.Logger:
    """Configure console and file logging for the application."""

    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("atlas")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    log_path = log_dir / "atlas.log"
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = RichHandler(rich_tracebacks=True, markup=False)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
