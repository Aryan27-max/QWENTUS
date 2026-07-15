"""Atlas command-line entry point."""

from __future__ import annotations

import argparse
import sys

from config import DEFAULT_CONFIG
from core.pipeline import AtlasPipeline, run_watch_mode
from llm.ollama import OllamaClient
from utils.logger import configure_logging


def parse_args() -> argparse.Namespace:
    """Parse command-line flags."""

    parser = argparse.ArgumentParser(description="Atlas offline AI resume screening system")
    parser.add_argument("--watch", action="store_true", help="Keep watching Incoming for new PDFs")
    return parser.parse_args()


def run_once() -> int:
    """Process all currently available resumes once."""

    config = DEFAULT_CONFIG
    config.ensure_directories()
    logger = configure_logging(config.paths.logs)
    client = OllamaClient(config)
    pipeline = AtlasPipeline(config=config, ollama=client, logger=logger)
    summary = pipeline.run_once()
    logger.info("Atlas completed: %s", summary.as_log_message())
    return 0


def main() -> int:
    """Execute Atlas."""

    args = parse_args()
    if args.watch:
        return run_watch_mode(DEFAULT_CONFIG)
    return run_once()


if __name__ == "__main__":
    raise SystemExit(main())
