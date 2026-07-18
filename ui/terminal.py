"""Rich terminal presentation for Atlas."""

from __future__ import annotations

import logging
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from colorama import just_fix_windows_console
from pyfiglet import figlet_format
from rich.align import Align
from rich.box import ROUNDED, SQUARE
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from config import AtlasConfig
from models.candidate import RunSummary


@dataclass(frozen=True)
class ResumeResult:
    """Parsed per-resume dashboard information."""

    index: int
    total: int
    resume_name: str
    overall_score: int
    decision: str
    processing_time: float
    eta: float
    ocr_status: str
    github_status: str
    linkedin_status: str
    portfolio_status: str


class AtlasConsoleHandler(logging.Handler):
    """Selective console log renderer for Atlas."""

    def __init__(self, ui: "AtlasTerminalUI") -> None:
        super().__init__(level=logging.INFO)
        self.ui = ui

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.ui.handle_log(record)
        except Exception:
            self.handleError(record)


class AtlasTerminalUI:
    """Render Atlas output as a polished terminal experience."""

    DASHBOARD_PATTERN = re.compile(
        r"^\[(?P<index>\d+)/(?:\s*)?(?P<total>\d+)\] (?P<resume>.+?) \| (?P<ocr>.+?) \| (?P<github>.+?) \| (?P<linkedin>.+?) \| (?P<portfolio>.+?) \| Overall (?P<overall>\d+) \| Decision (?P<decision>.+?) \| Time (?P<time>[0-9.]+) sec \| ETA (?P<eta>[0-9.]+) sec$"
    )

    def __init__(self, config: AtlasConfig, watch_mode: bool) -> None:
        just_fix_windows_console()
        self.config = config
        self.watch_mode = watch_mode
        self.console = Console()
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._run_started: float = time.perf_counter()
        self._results_seen: set[str] = set()
        self._warning_seen: set[str] = set()
        self._resume_scores: list[int] = []
        self._resume_times: list[float] = []
        self._decision_counts: dict[str, int] = {"Shortlisted": 0, "Maybe": 0, "Rejected": 0}
        self._failed_count = 0
        self._planned_total = 0
        self._current_resume = ""

    def create_log_handler(self) -> AtlasConsoleHandler:
        return AtlasConsoleHandler(self)

    def show_banner(self) -> None:
        art = figlet_format("QWENTUS", font="blocky")
        self.console.print()
        self.console.print(Align.center(Text(art, style="bold cyan")))
        self.console.print(Align.center(Text("QWENTUS v2.1.0", style="bold white")))
        self.console.print(Align.center(Text("Offline AI Resume Screening System by Aryan Gupta", style="dim white")))
        self.console.print(Align.center(Text(f"Powered by Ollama • {self.config.ollama_model}", style="cyan")))
        self.console.print()

    def show_processing_header(self, resumes_found: int) -> None:
        self._planned_total = resumes_found
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", justify="right")
        table.add_column(style="white")
        rows = [
            ("Workspace", str(self.config.paths.root)),
            ("Model", self.config.ollama_model),
            ("OCR Engine", "EasyOCR"),
            ("Watch Mode", "Enabled" if self.watch_mode else "Disabled"),
            ("Resumes Found", str(resumes_found)),
            ("Time Started", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ]
        for label, value in rows:
            table.add_row(label, value)
        self.console.print(Panel(table, title="Processing Header", border_style="cyan", box=ROUNDED))

    @contextmanager
    def progress_scope(self, total: int):
        if total <= 0:
            yield self
            return
        progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold]{task.fields[current]}[/bold]", justify="left"),
            BarColumn(bar_width=None),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            TextColumn("[magenta]{task.fields[speed]} res/min"),
            console=self.console,
            transient=False,
            expand=True,
        )
        self._progress = progress
        self._task_id = progress.add_task("Resumes", total=max(total, 1), current="Waiting for resumes...", speed="0.0")
        with progress:
            yield self
        self._progress = None
        self._task_id = None

    def handle_log(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if message.startswith("Starting batch with "):
            self._planned_total = self._extract_total(message) or self._planned_total
            return
        if message.startswith("Processing "):
            self._current_resume = message.removeprefix("Processing ").strip()
            self._update_progress(current=self._current_resume)
            return
        if match := self.DASHBOARD_PATTERN.match(message):
            result = ResumeResult(
                index=int(match.group("index")),
                total=int(match.group("total")),
                resume_name=match.group("resume").strip(),
                overall_score=int(match.group("overall")),
                decision=match.group("decision").strip(),
                processing_time=float(match.group("time")),
                eta=float(match.group("eta")),
                ocr_status=match.group("ocr").strip(),
                github_status=match.group("github").strip(),
                linkedin_status=match.group("linkedin").strip(),
                portfolio_status=match.group("portfolio").strip(),
            )
            self._render_result(result)
            return
        if record.levelno >= logging.ERROR:
            self._failed_count += 1
            self._render_warning("Failed", message, style="bright_red")
            return
        if record.levelno >= logging.WARNING:
            if self._should_render_warning(message):
                if "moving" in message.lower() and "failed" in message.lower():
                    self._failed_count += 1
                self._render_warning(self._warning_title(message), self._warning_reason(message))
            return
        if message == "No PDFs found in Incoming.":
            self.console.print(Panel(message, title="Atlas", border_style="cyan", box=SQUARE))
            return
        if message.startswith("Atlas watch mode started.") or message.startswith("Atlas watch mode stopped"):
            self.console.print(Panel(message, title="Watch Mode", border_style="cyan", box=SQUARE))
            return

    def show_completion(self, summary: RunSummary) -> None:
        self.console.print()
        self.console.print(Align.center(Text(figlet_format("COMPLETED", font="standard"), style="bold cyan")))
        total_runtime = time.perf_counter() - self._run_started
        average_score = round(sum(self._resume_scores) / len(self._resume_scores), 2) if self._resume_scores else 0
        average_processing_time = round(sum(self._resume_times) / len(self._resume_times), 2) if self._resume_times else 0
        total_processed = len(self._resume_scores) + self._failed_count
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan", justify="right")
        table.add_column(style="white")
        rows = [
            ("Processing Complete", "Yes"),
            ("Total Resumes", str(total_processed)),
            ("Shortlisted", str(self._decision_counts["Shortlisted"])),
            ("Maybe", str(self._decision_counts["Maybe"])),
            ("Rejected", str(self._decision_counts["Rejected"])),
            ("Failed", str(self._failed_count)),
            ("Average Score", f"{average_score:.2f}"),
            ("Average Processing Time", f"{average_processing_time:.2f} sec"),
            ("Total Runtime", f"{total_runtime:.2f} sec"),
            ("Excel Report Location", summary.report_file),
            ("Workspace Location", str(self.config.paths.root)),
        ]
        for label, value in rows:
            table.add_row(label, value)
        self.console.print(Panel(table, title="Processing Summary", border_style="green", box=ROUNDED))

    def _update_progress(self, current: str | None = None, total: int | None = None, completed: int | None = None, speed: float | None = None) -> None:
        if self._progress is None or self._task_id is None:
            return
        fields: dict[str, object] = {}
        if current is not None:
            fields["current"] = current
        if speed is not None:
            fields["speed"] = f"{speed:.1f}"
        if total is not None:
            fields["total"] = total
        if completed is not None:
            fields["completed"] = completed
        self._progress.update(self._task_id, **fields)

    def _render_result(self, result: ResumeResult) -> None:
        key = f"{result.index}:{result.resume_name}"
        if key in self._results_seen:
            return
        self._results_seen.add(key)
        self._resume_scores.append(result.overall_score)
        self._resume_times.append(result.processing_time)
        if result.decision in self._decision_counts:
            self._decision_counts[result.decision] += 1
        if result.total > self._planned_total:
            self._planned_total = result.total
        speed = 0.0
        elapsed = time.perf_counter() - self._run_started
        if elapsed > 0:
            speed = result.index / elapsed * 60.0
        self._update_progress(
            current=result.resume_name,
            total=max(self._planned_total, result.total),
            completed=result.index,
            speed=speed,
        )
        style = self._decision_style(result.decision)
        self.console.print()
        self.console.print(Rule(style=style))
        self.console.print(Align.center(Text(figlet_format(result.decision, font="standard"), style=style)))
        detail_table = Table.grid(padding=(0, 2))
        detail_table.add_column(style="bold", justify="right")
        detail_table.add_column(style="white")
        detail_table.add_row("Resume", result.resume_name)
        detail_table.add_row("Overall Score", str(result.overall_score))
        detail_table.add_row("Decision", result.decision)
        detail_table.add_row("Processing Time", f"{result.processing_time:.1f} sec")
        self.console.print(Panel(detail_table, border_style=style, box=ROUNDED))
        self._render_status_line(result)
        self.console.print(Rule(style=style))

    def _render_status_line(self, result: ResumeResult) -> None:
        statuses = [result.ocr_status, result.github_status, result.linkedin_status, result.portfolio_status]
        warnings = [status for status in statuses if status.startswith("⚠")]
        if result.ocr_status.startswith("✓ OCR Complete"):
            self._render_warning("OCR fallback enabled", f"{result.resume_name} used OCR to extract text.", style="yellow")
        for status in warnings:
            title = self._normalize_status_title(status)
            if title not in self._warning_seen:
                self._warning_seen.add(title)
                self._render_warning(title, "", style="yellow")

    def _render_warning(self, title: str, details: str, style: str = "yellow") -> None:
        key = f"{title}:{details}"
        if key in self._warning_seen and details:
            return
        self._warning_seen.add(key)
        body = details.strip() or "No additional details provided."
        self.console.print(Panel(body, title=f"⚠ {title}", border_style=style, box=ROUNDED))

    def _should_render_warning(self, message: str) -> bool:
        lowered = message.lower()
        if "retrying" in lowered:
            return False
        if "unavailable" in lowered or "missing" in lowered or "fallback" in lowered or "moving" in lowered or "internet connection" in lowered:
            return True
        return False

    def _warning_title(self, message: str) -> str:
        lowered = message.lower()
        if "github" in lowered:
            return "GitHub unavailable"
        if "linkedin" in lowered:
            return "LinkedIn unavailable"
        if "portfolio" in lowered:
            return "Portfolio unavailable"
        if "ocr" in lowered:
            return "OCR fallback enabled"
        if "internet connection" in lowered:
            return "Internet unavailable"
        if "failed to process" in lowered:
            return "Failed to process resume"
        if "moving" in lowered:
            return "Resume moved to Failed"
        return "Warning"

    def _warning_reason(self, message: str) -> str:
        if "Reason:" in message:
            return message.split("Reason:", 1)[1].strip().rstrip(".")
        if "Moving" in message and "Failed" in message:
            return message
        return message

    def _normalize_status_title(self, status: str) -> str:
        text = status.removeprefix("⚠ ").strip()
        lowered = text.lower()
        if "github" in lowered:
            return "GitHub unavailable"
        if "linkedin" in lowered:
            return "LinkedIn unavailable"
        if "portfolio" in lowered:
            return "Portfolio unavailable"
        return text or "Warning"

    def _extract_total(self, message: str) -> int | None:
        match = re.search(r"Starting batch with (\d+) PDF", message)
        return int(match.group(1)) if match else None

    def _decision_style(self, decision: str) -> str:
        return {
            "Shortlisted": "green",
            "Maybe": "yellow",
            "Rejected": "red",
            "Failed": "bright_red",
        }.get(decision, "cyan")