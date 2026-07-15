"""Logging tests."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import logging

from utils.logger import configure_logging


class LoggingTests(unittest.TestCase):
    def test_logger_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            logger = configure_logging(log_dir)
            logger.info("Atlas logging test")
            log_file = log_dir / "atlas.log"
            self.assertTrue(log_file.exists())
            for handler in list(logger.handlers):
                handler.flush()
                handler.close()
                logger.removeHandler(handler)
            logging.shutdown()


if __name__ == "__main__":
    unittest.main()
