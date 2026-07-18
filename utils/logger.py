"""Logging helpers for Atlas."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Callable


class ConciseConsoleHandler(logging.StreamHandler):
    """Stream handler that suppresses traceback rendering in the console."""

    def emit(self, record: logging.LogRecord) -> None:
        record_copy = copy.copy(record)
        record_copy.exc_info = None
        record_copy.exc_text = None
        record_copy.stack_info = None
        super().emit(record_copy)


_console_handler_factory: Callable[[], logging.Handler] | None = None


def set_console_handler_factory(factory: Callable[[], logging.Handler] | None) -> None:
    """Register a factory used to build the console handler for Atlas logs."""

    global _console_handler_factory
    _console_handler_factory = factory


def configure_logging(log_dir: Path, console_handler: logging.Handler | None = None) -> logging.Logger:
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

    if console_handler is None and _console_handler_factory is not None:
        console_handler = _console_handler_factory()
    if console_handler is None:
        console_handler = ConciseConsoleHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
