"""Atlas command-line entry point."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from config import DEFAULT_CONFIG, AtlasConfig, build_config
from core.pipeline import AtlasPipeline, run_watch_mode
from llm.ollama import OllamaClient
from ui.terminal import AtlasTerminalUI
from utils.logger import configure_logging, set_console_handler_factory

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def parse_args() -> argparse.Namespace:
    """Parse command-line flags."""

    parser = argparse.ArgumentParser(description="QWENTUS offline AI resume screening system by Aryan Gupta")
    parser.add_argument("--watch", action="store_true", help="Keep watching Incoming for new PDFs")
    parser.add_argument("--debug-one", type=Path, help="Process one resume and write debug artifacts")
    parser.add_argument("--root", type=Path, help="Workspace root directory (default from config/env)")
    parser.add_argument("--model", type=str, help="Ollama model name (default from config/env)")
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Console/file log level: DEBUG, INFO, WARNING, ERROR (default: INFO)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Reports/export directory (defaults to <root>/workspace/Reports)",
    )
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    level = str(args.log_level or "INFO").upper()
    if level not in _VALID_LOG_LEVELS:
        raise SystemExit(
            f"Invalid --log-level {args.log_level!r}; expected one of {sorted(_VALID_LOG_LEVELS)}"
        )
    args.log_level = level
    if args.root is not None and args.root.exists() and not args.root.is_dir():
        raise SystemExit(f"--root must be a directory: {args.root}")
    if args.output is not None and args.output.exists() and not args.output.is_dir():
        raise SystemExit(f"--output must be a directory: {args.output}")
    if args.model is not None and not str(args.model).strip():
        raise SystemExit("--model must be a non-empty string")


def config_from_args(args: argparse.Namespace) -> AtlasConfig:
    """Map CLI flags onto an AtlasConfig (env defaults still apply)."""

    return build_config(
        root=args.root,
        ollama_model=args.model,
        reports_dir=args.output,
    )


def _count_resume_pdfs(config: AtlasConfig = DEFAULT_CONFIG) -> int:
    return sum(1 for path in config.paths.incoming.glob("*.pdf") if path.is_file())


def run_once(
    args: argparse.Namespace | None = None,
    ui: AtlasTerminalUI | None = None,
    config: AtlasConfig | None = None,
) -> int:
    """Process all currently available resumes once."""

    config = config or DEFAULT_CONFIG
    config.ensure_directories()
    logger = configure_logging(config.paths.logs)
    if args is not None:
        logging.getLogger().setLevel(getattr(logging, args.log_level.upper(), logging.INFO))
    client = OllamaClient(config)
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
    _validate_args(args)
    config = config_from_args(args)
    ui = AtlasTerminalUI(config=config, watch_mode=args.watch)
    set_console_handler_factory(ui.create_log_handler)
    ui.show_banner()
    resumes_found = _count_resume_pdfs(config)
    ui.show_processing_header(resumes_found=resumes_found)
    with ui.progress_scope(resumes_found):
        if args.watch:
            return run_watch_mode(config, completion_callback=ui.show_completion)
        return run_once(args, ui=ui, config=config)


if __name__ == "__main__":
    raise SystemExit(main())
