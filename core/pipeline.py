"""Atlas orchestration pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Iterable
import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from agents.evaluator import CandidateEvaluator, EvaluationOutcome, FatalEvaluationError, ProfileParseError
from config import AtlasConfig
from exporters.excel import ExcelExporter
from llm.ollama import OllamaClient
from models.candidate import RunSummary, ScreeningRecord
from parsers.pdf_parser import PDFParseError
from scrapers.common import NetworkMonitor, has_internet_connectivity
from config import AtlasPaths


@dataclass(frozen=True)
class ProcessOutcome:
    """Outcome for one processed resume."""

    pdf_path: Path
    evaluation: EvaluationOutcome | None = None
    failure_reason: str = ""


@dataclass
class PipelineStats:
    """Rolling timing and decision metrics for the recruiter dashboard."""

    total: int
    processed: int = 0
    shortlisted: int = 0
    maybe: int = 0
    rejected: int = 0
    failed: int = 0
    total_processing_time: float = 0.0
    total_llm_time: float = 0.0
    total_ocr_time: float = 0.0
    total_scrape_time: float = 0.0
    total_excel_time: float = 0.0
    total_move_time: float = 0.0
    minimum_total_time: float = float("inf")
    maximum_total_time: float = 0.0
    run_started: float = time.perf_counter()

    def seed(self, records: list[ScreeningRecord]) -> None:
        for record in records:
            if record.decision == "Shortlisted":
                self.shortlisted += 1
            elif record.decision == "Maybe":
                self.maybe += 1
            else:
                self.rejected += 1
            self.total_processing_time += record.processing_time_seconds
            if record.processing_time_seconds:
                self.minimum_total_time = min(self.minimum_total_time, record.processing_time_seconds)
                self.maximum_total_time = max(self.maximum_total_time, record.processing_time_seconds)

    def update(self, record: ScreeningRecord | None, timings: dict[str, float], failed: bool = False) -> None:
        if failed:
            self.failed += 1
        elif record is not None:
            self.processed += 1
            if record.decision == "Shortlisted":
                self.shortlisted += 1
            elif record.decision == "Maybe":
                self.maybe += 1
            else:
                self.rejected += 1
        resume_total = timings.get("total", 0.0)
        self.total_processing_time += resume_total
        self.total_llm_time += timings.get("llm", 0.0)
        self.total_ocr_time += timings.get("ocr", 0.0)
        self.total_scrape_time += timings.get("scrape", timings.get("github", 0.0) + timings.get("linkedin", 0.0) + timings.get("portfolio", 0.0))
        self.total_excel_time += timings.get("excel", 0.0)
        self.total_move_time += timings.get("move", 0.0)
        self.minimum_total_time = min(self.minimum_total_time, resume_total)
        self.maximum_total_time = max(self.maximum_total_time, resume_total)

    def average_processing_time(self) -> float:
        return self.total_processing_time / self.processed if self.processed else 0.0

    def average_llm_time(self) -> float:
        return self.total_llm_time / self.processed if self.processed else 0.0

    def average_ocr_time(self) -> float:
        return self.total_ocr_time / self.processed if self.processed else 0.0

    def average_scrape_time(self) -> float:
        return self.total_scrape_time / self.processed if self.processed else 0.0

    def average_excel_time(self) -> float:
        return self.total_excel_time / self.processed if self.processed else 0.0

    def average_move_time(self) -> float:
        return self.total_move_time / self.processed if self.processed else 0.0

    def total_runtime(self) -> float:
        return time.perf_counter() - self.run_started

    def estimated_remaining_time(self) -> float:
        remaining = max(self.total - self.processed, 0)
        return remaining * self.average_processing_time()


class AtlasPipeline:
    """Process resumes through the full Atlas workflow."""

    def __init__(self, config: AtlasConfig, ollama: OllamaClient, logger: logging.Logger) -> None:
        self.config = config
        self.ollama = ollama
        self.logger = logger
        self.internet_available = has_internet_connectivity()
        self.network_monitor = NetworkMonitor(config)
        self.evaluator = CandidateEvaluator(
            config,
            ollama,
            logger=logger,
            internet_available=self.internet_available,
            network_monitor=self.network_monitor,
        )
        self.exporter = ExcelExporter(config)
        self._checkpoint: dict[str, dict[str, str]] = self._load_checkpoint()

    def _load_checkpoint(self) -> dict[str, dict[str, str]]:
        if not self.config.paths.checkpoint.exists():
            return {}
        try:
            payload = json.loads(self.config.paths.checkpoint.read_text(encoding="utf-8"))
        except Exception:
            return {}
        completed = payload.get("completed", {})
        return completed if isinstance(completed, dict) else {}

    def _save_checkpoint(self) -> None:
        self.config.paths.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        payload = {"completed": self._checkpoint, "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self.config.paths.checkpoint.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def _resume_key(self, pdf_path: Path) -> str:
        return pdf_path.name

    def _restore_completed_resume(self, pdf_path: Path) -> bool:
        key = self._resume_key(pdf_path)
        entry = self._checkpoint.get(key)
        if not entry:
            return False
        decision = entry.get("decision", "")
        destination = {
            "Shortlisted": self.config.paths.shortlisted,
            "Maybe": self.config.paths.maybe,
            "Rejected": self.config.paths.rejected,
        }.get(decision)
        if destination is None:
            return False
        if pdf_path.exists():
            self._move_pdf(pdf_path, destination)
        return True

    def _seed_existing_records(self) -> list[ScreeningRecord]:
        records = self.exporter.load_existing_records()
        records.sort(key=lambda item: item.overall_score, reverse=True)
        for rank, record in enumerate(records, start=1):
            record.rank = rank
        return records

    def run_once(self) -> RunSummary:
        """Process the current Incoming folder exactly once."""

        self.config.ensure_directories()
        self.ollama.ensure_ready()
        if not self.internet_available:
            self.logger.warning(
                "Internet connection unavailable. Skipping external profile scraping. Continuing with resume-only evaluation."
            )
        records = self._seed_existing_records()
        completed_names = {record.resume_file for record in records if record.resume_file}
        incoming_paths = list(self._iter_pdf_paths(self.config.paths.incoming))
        pdf_paths = []
        for path in incoming_paths:
            if path.name in completed_names or self._restore_completed_resume(path):
                continue
            pdf_paths.append(path)
        stats = PipelineStats(total=len(pdf_paths))
        stats.seed(records)
        if not pdf_paths:
            self.exporter.export(records, stats)
            self.logger.info("No PDFs found in Incoming.")
            return RunSummary(processed=0, shortlisted=stats.shortlisted, maybe=stats.maybe, rejected=stats.rejected, failed=stats.failed, report_file=str(self.config.paths.workbook))

        self.logger.info("Starting batch with %s PDF(s)", len(pdf_paths))
        self.exporter.export(records, stats)
        for index, pdf_path in enumerate(pdf_paths, start=1):
            outcome = self._process_pdf(pdf_path)
            if outcome.evaluation is None:
                stats.update(None, {"total": 0.0, "llm": 0.0, "ocr": 0.0, "scrape": 0.0, "move": 0.0, "excel": 0.0}, failed=True)
                self._move_pdf(outcome.pdf_path, self.config.paths.failed)
                self.exporter.export(records, stats)
                self._render_dashboard(records, stats, current_pdf=outcome.pdf_path.name, current_index=index, latest_timings={"ocr_used": 0.0, "total": 0.0})
                continue
            record = self._to_record(outcome.evaluation)
            records.append(record)
            records.sort(key=lambda item: item.overall_score, reverse=True)
            for rank, ranked_record in enumerate(records, start=1):
                ranked_record.rank = rank
            destination = self._destination_for_record(record)
            move_started = time.perf_counter()
            self._move_pdf(outcome.pdf_path, destination)
            move_time = time.perf_counter() - move_started
            record.processing_time_seconds = sum(outcome.evaluation.timings.get(key, 0.0) for key in ("pdf", "ocr", "github", "linkedin", "portfolio", "llm")) + move_time
            timings = dict(outcome.evaluation.timings)
            timings["move"] = move_time
            timings["scrape"] = sum(timings.get(key, 0.0) for key in ("github", "linkedin", "portfolio"))
            timings["total"] = record.processing_time_seconds
            excel_started = time.perf_counter()
            self.exporter.export(records, stats)
            timings["excel"] = time.perf_counter() - excel_started
            stats.update(record, timings, failed=False)
            self._checkpoint[record.resume_file] = {"decision": record.decision, "destination": destination.name}
            self._save_checkpoint()
            self._render_dashboard(records, stats, current_pdf=outcome.pdf_path.name, current_index=index, latest_record=record, latest_timings=timings)

        report_path = self.exporter.export(records, stats)
        summary = RunSummary(
            processed=len(records),
            shortlisted=stats.shortlisted,
            maybe=stats.maybe,
            rejected=stats.rejected,
            failed=stats.failed,
            report_file=str(report_path),
        )
        return summary

    def _process_pdf(self, pdf_path: Path) -> ProcessOutcome:
        """Build and score one resume while keeping failures isolated."""

        try:
            self.logger.info("Processing %s", pdf_path.name)
            return ProcessOutcome(pdf_path=pdf_path, evaluation=self.evaluator.evaluate_with_timing(pdf_path))
        except (PDFParseError, ProfileParseError) as exc:
            self.logger.warning("%s. Moving %s to Failed.", exc, pdf_path.name)
            return ProcessOutcome(pdf_path=pdf_path, failure_reason=str(exc))
        except (FatalEvaluationError,) as exc:
            self.logger.warning("%s. Moving %s to Failed.", exc, pdf_path.name)
            return ProcessOutcome(pdf_path=pdf_path, failure_reason=str(exc))
        except Exception as exc:
            self.logger.exception("Failed to process %s: %s", pdf_path, exc)
            return ProcessOutcome(pdf_path=pdf_path, failure_reason=str(exc))

    def _to_record(self, outcome: EvaluationOutcome) -> ScreeningRecord:
        profile = outcome.profile
        evaluation = outcome.evaluation
        decision = self.config.decision_for_score(evaluation.overall_score)
        return ScreeningRecord(
            rank=0,
            candidate_name=evaluation.name,
            email=evaluation.email,
            phone=profile.phone,
            college=profile.college,
            degree=profile.degree,
            overall_score=evaluation.overall_score,
            technical_score=evaluation.technical_score,
            github_score=evaluation.github_score,
            skills_score=evaluation.skills_score,
            projects_score=evaluation.projects_score,
            experience_score=evaluation.experience_score,
            leadership_score=evaluation.leadership_score,
            communication_score=evaluation.communication_score,
            achievements_score=evaluation.achievements_score,
            resume_quality_score=evaluation.resume_quality_score,
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

    def _move_pdf(self, source: Path, destination_dir: Path) -> bool:
        """Move the processed PDF into the final decision folder."""

        destination_dir.mkdir(parents=True, exist_ok=True)
        target = destination_dir / source.name
        if not source.exists():
            self.logger.warning("PDF already moved or unavailable. Resume evaluation already completed. Skipping file move.")
            return False
        if target.exists():
            try:
                target.unlink()
            except (PermissionError, OSError):
                self.logger.warning("Destination already exists for %s. Skipping file replacement.", source.name)
                return False
        delays = [0.5, 0.5, 0.5]
        for attempt in range(4):
            if attempt:
                time.sleep(delays[attempt - 1])
            try:
                shutil.move(str(source), str(target))
                self.logger.info("Moved %s to %s", source.name, destination_dir.name)
                return True
            except FileNotFoundError:
                self.logger.warning("PDF already moved or unavailable. Resume evaluation already completed. Skipping file move.")
                return False
            except PermissionError as exc:
                if attempt < 3:
                    continue
                self.logger.warning("Failed to move %s to %s after retries: %s", source.name, destination_dir.name, exc)
                return False
            except OSError as exc:
                if attempt < 3 and getattr(exc, "winerror", None) in {5, 32}:
                    continue
                self.logger.warning("Failed to move %s to %s after retries: %s", source.name, destination_dir.name, exc)
                return False
        return False

    def _render_dashboard(self, records: list[ScreeningRecord], stats: PipelineStats, current_pdf: str, current_index: int, latest_record: ScreeningRecord | None = None, latest_timings: dict[str, float] | None = None) -> None:
        total = stats.total or max(current_index, 1)
        decision = latest_record.decision if latest_record else "Failed"
        overall_score = latest_record.overall_score if latest_record else 0
        total_seconds = latest_record.processing_time_seconds if latest_record else stats.average_processing_time()
        ocr_status = "✓ OCR Complete" if latest_timings and latest_timings.get("ocr_used", 0.0) > 0 else "✓ OCR Skipped"
        github_status = self._source_status(latest_record, "github")
        linkedin_status = self._source_status(latest_record, "linkedin")
        portfolio_status = self._source_status(latest_record, "portfolio")
        self.logger.info(
            "[%s/%s] %s | %s | %s | %s | %s | Overall %s | Decision %s | Time %.1f sec | ETA %.1f sec",
            current_index,
            total,
            current_pdf,
            ocr_status,
            github_status,
            linkedin_status,
            portfolio_status,
            overall_score,
            decision,
            total_seconds,
            stats.estimated_remaining_time(),
        )

    def _source_status(self, record: ScreeningRecord | None, source: str) -> str:
        if record is None:
            return ""
        value = {
            "github": record.github_url,
            "linkedin": record.linkedin_url,
            "portfolio": record.portfolio_url,
        }.get(source, "")
        if not value:
            labels = {
                "github": "GitHub unavailable",
                "linkedin": "LinkedIn unavailable",
                "portfolio": "Portfolio unavailable",
            }
            return f"⚠ {labels.get(source, source.title() + ' unavailable')}"
        labels = {
            "github": "GitHub Parsed",
            "linkedin": "LinkedIn Parsed",
            "portfolio": "Portfolio Parsed",
        }
        return f"✓ {labels.get(source, source.title() + ' Parsed')}"

    def _iter_pdf_paths(self, folder: Path) -> Iterable[Path]:
        return sorted(path for path in folder.glob("*.pdf") if path.is_file())

    def run_debug_one(self, pdf_path: Path) -> int:
        """Process one resume and save debug artifacts."""

        self.config.ensure_directories()
        self.ollama.ensure_ready()
        outcome = self.evaluator.evaluate_path_with_details(pdf_path)
        if outcome.evaluation is None:
            self.logger.error("Debug run failed for %s", pdf_path.name)
            return 1

        record = self._to_record(outcome)
        record.processing_time_seconds = sum(outcome.timings.get(key, 0.0) for key in ("pdf", "ocr", "github", "linkedin", "portfolio", "llm"))
        record.rank = 1
        stats = PipelineStats(total=1)
        stats.update(record, {**outcome.timings, "scrape": sum(outcome.timings.get(key, 0.0) for key in ("github", "linkedin", "portfolio")), "move": 0.0, "excel": 0.0, "total": record.processing_time_seconds}, failed=False)
        self.exporter.export([record], stats)
        self._write_debug_artifacts(pdf_path, outcome)
        return 0

    def _write_debug_artifacts(self, pdf_path: Path, outcome: EvaluationOutcome) -> None:
        debug_dir = self.config.paths.debug / pdf_path.stem
        debug_dir.mkdir(parents=True, exist_ok=True)
        profile = outcome.profile
        evaluation = outcome.evaluation
        payload = {
            "extracted_text": profile.resume_excerpt[: self.config.max_debug_artifact_chars],
            "source_summaries": {key: value[: self.config.max_debug_artifact_chars] for key, value in profile.source_summaries.items()},
            "prompt": outcome.prompt[: self.config.max_debug_artifact_chars],
            "raw_llm_response": outcome.raw_response,
            "evaluation": evaluation.model_dump(),
            "timings": outcome.timings,
            "prompt_stats": outcome.prompt_stats or {},
        }
        (debug_dir / "prompt.txt").write_text(outcome.prompt, encoding="utf-8")
        (debug_dir / "raw-llm-response.json").write_text(json.dumps(outcome.raw_response, indent=2, ensure_ascii=False), encoding="utf-8")
        (debug_dir / "validated-json.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


class _ResumeWatchHandler(FileSystemEventHandler):
    """Watchdog bridge that funnels new PDFs into the pipeline."""

    def __init__(self, queue, logger: logging.Logger, should_queue=None) -> None:
        self.queue = queue
        self.logger = logger
        self.should_queue = should_queue

    def on_created(self, event) -> None:  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        path = Path(event.src_path)
        if path.suffix.lower() == ".pdf":
            if self.should_queue is not None and not self.should_queue(path):
                self.logger.info("Skipping duplicate resume event %s", path.name)
                return
            self.logger.info("Queued new resume %s", path.name)
            self.queue.put(path)


def run_watch_mode(config: AtlasConfig, completion_callback=None) -> int:
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
        ollama.close()
        return 1

    pipeline = AtlasPipeline(config=config, ollama=ollama, logger=logger)
    from core.queue import ResumePathQueue

    resume_queue = ResumePathQueue()
    state_lock = threading.Lock()
    queued_signatures: set[tuple[str, int, int]] = set()
    active_signatures: set[tuple[str, int, int]] = set()
    completed_signatures: set[tuple[str, int, int]] = set()

    def _signature(path: Path) -> tuple[str, int, int] | None:
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        return (path.name, stat.st_size, stat.st_mtime_ns)

    def _should_queue(path: Path) -> bool:
        signature = _signature(path)
        if signature is None:
            return False
        with state_lock:
            if signature in queued_signatures or signature in active_signatures or signature in completed_signatures:
                return False
            queued_signatures.add(signature)
            return True

    handler = _ResumeWatchHandler(resume_queue, logger, _should_queue)
    observer = Observer()
    observer.schedule(handler, str(config.paths.incoming), recursive=False)
    observer.start()
    logger.info("Atlas watch mode started.")

    stats = PipelineStats(total=0)
    records: list[ScreeningRecord] = []
    last_completion_index = 0
    try:
        initial_paths = sorted(config.paths.incoming.glob("*.pdf"))
        stats.total = len(initial_paths)
        for path in initial_paths:
            if _should_queue(path):
                resume_queue.put(path)
        current_index = 0
        while True:
            try:
                path = resume_queue.get(timeout=1.0)
            except queue_module.Empty:
                if completion_callback is not None and current_index > last_completion_index:
                    summary = RunSummary(
                        processed=len(records),
                        shortlisted=stats.shortlisted,
                        maybe=stats.maybe,
                        rejected=stats.rejected,
                        failed=stats.failed,
                        report_file=str(config.paths.workbook),
                    )
                    completion_callback(summary)
                    last_completion_index = current_index
                continue
            signature = _signature(path)
            if signature is None:
                logger.warning("PDF already moved or unavailable. Resume evaluation already completed. Skipping file move.")
                continue
            with state_lock:
                if signature in active_signatures or signature in completed_signatures:
                    logger.info("Skipping duplicate resume event for %s", path.name)
                    continue
                active_signatures.add(signature)
            current_index += 1
            stats.total = max(stats.total, current_index)
            try:
                outcome = pipeline._process_pdf(path)
                if outcome.evaluation is None:
                    stats.update(None, {"total": 0.0, "llm": 0.0, "ocr": 0.0}, failed=True)
                    pipeline.exporter.export(records, stats)
                    pipeline._move_pdf(outcome.pdf_path, config.paths.failed)
                    pipeline._render_dashboard(records, stats, current_pdf=path.name, current_index=current_index, latest_timings={"ocr_used": 0.0, "total": 0.0})
                    continue
                record = pipeline._to_record(outcome.evaluation)
                records.append(record)
                records.sort(key=lambda item: item.overall_score, reverse=True)
                for rank, ranked_record in enumerate(records, start=1):
                    ranked_record.rank = rank
                destination = pipeline._destination_for_record(record)
                timings = dict(outcome.evaluation.timings)
                timings["scrape"] = sum(timings.get(key, 0.0) for key in ("github", "linkedin", "portfolio"))
                record.processing_time_seconds = sum(timings.get(key, 0.0) for key in ("pdf", "ocr", "github", "linkedin", "portfolio", "llm"))
                timings["total"] = record.processing_time_seconds
                stats.update(record, timings, failed=False)
                pipeline.exporter.export(records, stats)
                pipeline._checkpoint[record.resume_file] = {"decision": record.decision, "destination": destination.name}
                pipeline._save_checkpoint()
                folder_started = time.perf_counter()
                moved = pipeline._move_pdf(outcome.pdf_path, destination)
                folder_time = time.perf_counter() - folder_started
                timings["folder"] = folder_time
                record.processing_time_seconds += folder_time
                timings["total"] = record.processing_time_seconds
                stats.total_processing_time += folder_time
                stats.total_move_time += folder_time
                stats.minimum_total_time = min(stats.minimum_total_time, record.processing_time_seconds)
                stats.maximum_total_time = max(stats.maximum_total_time, record.processing_time_seconds)
                pipeline._render_dashboard(records, stats, current_pdf=path.name, current_index=current_index, latest_record=record, latest_timings=timings)
            finally:
                with state_lock:
                    active_signatures.discard(signature)
                    completed_signatures.add(signature)

    except KeyboardInterrupt:
        logger.info("Atlas watch mode stopped by user.")
    finally:
        observer.stop()
        observer.join()
        ollama.close()
    return 0
