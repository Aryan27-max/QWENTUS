"""Atlas command-line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from config import DEFAULT_CONFIG
from core.pipeline import AtlasPipeline, run_watch_mode
from llm.ollama import OllamaClient
from ui.terminal import AtlasTerminalUI
from utils.logger import configure_logging, set_console_handler_factory


def parse_args() -> argparse.Namespace:
    """Parse command-line flags."""

    parser = argparse.ArgumentParser(description="QWENTUS offline AI resume screening system by Aryan Gupta")
    parser.add_argument("--watch", action="store_true", help="Keep watching Incoming for new PDFs")
    parser.add_argument("--debug-one", type=Path, help="Process one resume and write debug artifacts")
    return parser.parse_args()


def _count_resume_pdfs(config=DEFAULT_CONFIG) -> int:
    return sum(1 for path in config.paths.incoming.glob("*.pdf") if path.is_file())


def run_once(args: argparse.Namespace | None = None, ui: AtlasTerminalUI | None = None) -> int:
    """Process all currently available resumes once."""

    config = DEFAULT_CONFIG
    config.ensure_directories()
    logger = configure_logging(config.paths.logs)
    with OllamaClient(config) as client:
        pipeline = AtlasPipeline(config=config, ollama=client, logger=logger)
        if args and args.debug_one:
            return pipeline.run_debug_one(args.debug_one)
        summary = pipeline.run_once()
    if ui is not None:
        ui.show_completion(summary)
    else:
        logger.info("Atlas completed: %s", summary.as_log_message())
    return 0


def main() -> int:
    """Execute Atlas."""

    args = parse_args()
    config = DEFAULT_CONFIG
    ui = AtlasTerminalUI(config=config, watch_mode=args.watch)
    set_console_handler_factory(ui.create_log_handler)
    ui.show_banner()
    resumes_found = _count_resume_pdfs(config)
    ui.show_processing_header(resumes_found=resumes_found)
    with ui.progress_scope(resumes_found):
        if args.watch:
            return run_watch_mode(config, completion_callback=ui.show_completion)
        return run_once(args, ui=ui)


if __name__ == "__main__":
    raise SystemExit(main())
