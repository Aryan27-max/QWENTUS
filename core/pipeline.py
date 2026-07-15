"""Atlas orchestration pipeline."""

from __future__ import annotations

import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agents.evaluator import CandidateEvaluator, EvaluationOutcome
from config import AtlasConfig
from exporters.excel import ExcelExporter
from llm.ollama import OllamaClient
from models.candidate import RunSummary, ScreeningRecord


class AtlasPipeline:
    """Process resumes through the full Atlas workflow."""

    def __init__(self, config: AtlasConfig, ollama: OllamaClient, logger: logging.Logger) -> None:
        self.config = config
        self.ollama = ollama
        self.logger = logger
        self.evaluator = CandidateEvaluator(config, ollama)
        self.exporter = ExcelExporter(config)

    def run_once(self) -> RunSummary:
        """Process the current Incoming folder exactly once."""

        self.config.ensure_directories()
        self.ollama.ensure_ready()
        pdf_paths = list(self._iter_pdf_paths(self.config.paths.incoming))
        if not pdf_paths:
            self.logger.info("No PDFs found in Incoming.")
            return RunSummary()

        self.logger.info("Starting batch with %s PDF(s)", len(pdf_paths))
        records: list[ScreeningRecord] = []
        shortlisted = maybe = rejected = failed = 0

        with ThreadPoolExecutor(max_workers=self.config.preprocess_workers) as executor:
            for outcome in executor.map(self._process_pdf, pdf_paths):
                if outcome is None:
                    failed += 1
                    continue
                record = self._to_record(outcome)
                records.append(record)
                destination = self._destination_for_record(record)
                self._move_pdf(Path(outcome.profile.resume_file), destination)
                if record.decision == "Shortlisted":
                    shortlisted += 1
                elif record.decision == "Maybe":
                    maybe += 1
                else:
                    rejected += 1

        records.sort(key=lambda item: item.overall_score, reverse=True)
        for index, record in enumerate(records, start=1):
            record.rank = index

        report_path = self.exporter.export(records)
        summary = RunSummary(
            processed=len(records),
            shortlisted=shortlisted,
            maybe=maybe,
            rejected=rejected,
            failed=failed,
            report_file=str(report_path),
        )
        return summary

    def _process_pdf(self, pdf_path: Path) -> EvaluationOutcome | None:
        """Build and score one resume while keeping failures isolated."""

        try:
            self.logger.info("Processing %s", pdf_path.name)
            return self.evaluator.evaluate_path(pdf_path)
        except Exception as exc:
            self.logger.exception("Failed to process %s: %s", pdf_path, exc)
            return None

    def _to_record(self, outcome: EvaluationOutcome) -> ScreeningRecord:
        profile = outcome.profile
        evaluation = outcome.evaluation
        decision = self.config.decision_for_score(evaluation.overall_score)
        return ScreeningRecord(
            rank=0,
            candidate_name=evaluation.name or profile.name,
            email=evaluation.email or profile.email,
            phone=profile.phone,
            college=profile.college,
            degree=profile.degree,
            overall_score=evaluation.overall_score,
            technical_score=evaluation.technical_score,
            github_score=evaluation.github_score,
            projects_score=evaluation.projects_score,
            leadership_score=evaluation.leadership_score,
            communication_score=evaluation.communication_score,
            achievements_score=evaluation.achievements_score,
            strengths=", ".join(evaluation.strengths),
            weaknesses=", ".join(evaluation.weaknesses),
            recommendation=evaluation.recommendation,
            decision=decision,
            summary=evaluation.summary,
            resume_file=profile.resume_name,
            github_url=profile.links.github_url,
            linkedin_url=profile.links.linkedin_url,
            portfolio_url=profile.links.portfolio_url,
        )

    def _destination_for_record(self, record: ScreeningRecord) -> Path:
        if record.decision == "Shortlisted":
            return self.config.paths.shortlisted
        if record.decision == "Maybe":
            return self.config.paths.maybe
        return self.config.paths.rejected

    def _move_pdf(self, source: Path, destination_dir: Path) -> None:
        """Move the processed PDF into the final decision folder."""

        destination_dir.mkdir(parents=True, exist_ok=True)
        target = destination_dir / source.name
        if target.exists():
            target.unlink()
        shutil.move(str(source), str(target))
        self.logger.info("Moved %s to %s", source.name, destination_dir.name)

    def _iter_pdf_paths(self, folder: Path) -> Iterable[Path]:
        return sorted(path for path in folder.glob("*.pdf") if path.is_file())


class _ResumeWatchHandler(FileSystemEventHandler):
    """Watchdog bridge that funnels new PDFs into the pipeline."""

    def __init__(self, queue, logger: logging.Logger) -> None:
        self.queue = queue
        self.logger = logger

    def on_created(self, event) -> None:  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        path = Path(event.src_path)
        if path.suffix.lower() == ".pdf":
            self.logger.info("Queued new resume %s", path.name)
            self.queue.put(path)


def run_watch_mode(config: AtlasConfig) -> int:
    """Monitor Incoming for new resumes and process them one-by-one."""

    import queue as queue_module

    config.ensure_directories()
    from utils.logger import configure_logging

    logger = configure_logging(config.paths.logs)
    ollama = OllamaClient(config)
    try:
        ollama.ensure_ready()
    except Exception as exc:
        logger.error(str(exc))
        return 1

    pipeline = AtlasPipeline(config=config, ollama=ollama, logger=logger)
    from core.queue import ResumePathQueue

    resume_queue = ResumePathQueue()
    handler = _ResumeWatchHandler(resume_queue, logger)
    observer = Observer()
    observer.schedule(handler, str(config.paths.incoming), recursive=False)
    observer.start()
    logger.info("Atlas watch mode started.")

    try:
        for path in sorted(config.paths.incoming.glob("*.pdf")):
            resume_queue.put(path)
        while True:
            try:
                path = resume_queue.get(timeout=1.0)
            except queue_module.Empty:
                continue
            outcome = pipeline._process_pdf(path)
            if outcome is None:
                continue
            record = pipeline._to_record(outcome)
            destination = pipeline._destination_for_record(record)
            pipeline._move_pdf(Path(outcome.profile.resume_file), destination)
    except KeyboardInterrupt:
        logger.info("Atlas watch mode stopped by user.")
    finally:
        observer.stop()
        observer.join()
    return 0
