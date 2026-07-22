"""Atlas configuration.

Defaults stay stable for local demos; runtime values can be overridden via
environment variables (and optionally CLI flags) without editing source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value.strip()


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


WORKSPACE_ROOT = Path(_env_str("QWENTUS_ROOT", r"c:\this is dekstop\atlas"))
OLLAMA_BASE_URL = _env_str("QWENTUS_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = _env_str("QWENTUS_OLLAMA_MODEL", "qwen3:8b")

SHORTLIST_THRESHOLD = _env_int("QWENTUS_SHORTLIST_THRESHOLD", 60)
MAYBE_THRESHOLD = _env_int("QWENTUS_MAYBE_THRESHOLD", 50)

PREPROCESS_WORKERS = _env_int("QWENTUS_PREPROCESS_WORKERS", 6)
OLLAMA_TIMEOUT_SECONDS = _env_int("QWENTUS_OLLAMA_TIMEOUT_SECONDS", 60)
OLLAMA_MAX_RETRIES = _env_int("QWENTUS_OLLAMA_MAX_RETRIES", 1)
OLLAMA_RETRY_DELAYS = (0, 1)
OLLAMA_TEMPERATURE = _env_float("QWENTUS_OLLAMA_TEMPERATURE", 0.0)
OLLAMA_TOP_P = _env_float("QWENTUS_OLLAMA_TOP_P", 0.9)
OLLAMA_TOP_K = _env_int("QWENTUS_OLLAMA_TOP_K", 40)
OLLAMA_NUM_CTX = _env_int("QWENTUS_OLLAMA_NUM_CTX", 8192)
OLLAMA_NUM_PREDICT = _env_int("QWENTUS_OLLAMA_NUM_PREDICT", 256)
OLLAMA_THINK = _env_bool("QWENTUS_OLLAMA_THINK", False)
REQUEST_TIMEOUT_SECONDS = _env_int("QWENTUS_REQUEST_TIMEOUT_SECONDS", 20)
OCR_TIMEOUT_SECONDS = _env_int("QWENTUS_OCR_TIMEOUT_SECONDS", 60)
OCR_MAX_RETRIES = 1
OCR_RETRY_DELAYS = (0, 1)
MAX_RESUME_EXCERPT_CHARS = 2500
MAX_SCRAPED_TEXT_CHARS = 2500
MAX_LINKS_PER_RESUME = 5
MAX_PROMPT_CHARS = 5000
MAX_PROMPT_ESTIMATED_TOKENS = 1300
MAX_SOURCE_SUMMARY_CHARS = 1500
MAX_DEBUG_ARTIFACT_CHARS = 20000
NETWORK_FAILURE_THRESHOLD = 5
NETWORK_RECOVERY_SECONDS = 300
PROGRESS_REFRESH_SECONDS = 1.0
DNS_RESOLVERS = ("1.1.1.1", "8.8.8.8")


@dataclass(frozen=True)
class AtlasPaths:
    """Filesystem locations used by Atlas."""

    root: Path = WORKSPACE_ROOT
    workspace: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace")
    incoming: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Incoming")
    processing: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Processing")
    shortlisted: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Shortlisted")
    maybe: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Maybe")
    rejected: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Rejected")
    failed: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Failed")
    reports: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Reports")
    workbook: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Reports" / "Candidates.xlsx")
    debug: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Debug")
    checkpoint: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Reports" / "atlas_checkpoint.json")
    logs: Path = field(default_factory=lambda: WORKSPACE_ROOT / "logs")
    docs: Path = field(default_factory=lambda: WORKSPACE_ROOT / "docs")

    def __post_init__(self) -> None:
        default_paths = {
            "workspace": WORKSPACE_ROOT / "workspace",
            "incoming": WORKSPACE_ROOT / "workspace" / "Incoming",
            "processing": WORKSPACE_ROOT / "workspace" / "Processing",
            "shortlisted": WORKSPACE_ROOT / "workspace" / "Shortlisted",
            "maybe": WORKSPACE_ROOT / "workspace" / "Maybe",
            "rejected": WORKSPACE_ROOT / "workspace" / "Rejected",
            "failed": WORKSPACE_ROOT / "workspace" / "Failed",
            "reports": WORKSPACE_ROOT / "workspace" / "Reports",
            "workbook": WORKSPACE_ROOT / "workspace" / "Reports" / "Candidates.xlsx",
            "debug": WORKSPACE_ROOT / "workspace" / "Debug",
            "checkpoint": WORKSPACE_ROOT / "workspace" / "Reports" / "atlas_checkpoint.json",
            "logs": WORKSPACE_ROOT / "logs",
            "docs": WORKSPACE_ROOT / "docs",
        }
        derived_paths = {
            "workspace": self.root / "workspace",
            "incoming": self.root / "workspace" / "Incoming",
            "processing": self.root / "workspace" / "Processing",
            "shortlisted": self.root / "workspace" / "Shortlisted",
            "maybe": self.root / "workspace" / "Maybe",
            "rejected": self.root / "workspace" / "Rejected",
            "failed": self.root / "workspace" / "Failed",
            "reports": self.root / "workspace" / "Reports",
            "workbook": self.root / "workspace" / "Reports" / "Candidates.xlsx",
            "debug": self.root / "workspace" / "Debug",
            "checkpoint": self.root / "workspace" / "Reports" / "atlas_checkpoint.json",
            "logs": self.root / "logs",
            "docs": self.root / "docs",
        }
        for field_name, default_value in default_paths.items():
            current_value = getattr(self, field_name)
            if current_value == default_value and self.root != WORKSPACE_ROOT:
                object.__setattr__(self, field_name, derived_paths[field_name])


@dataclass(frozen=True)
class AtlasConfig:
    """Runtime configuration for Atlas."""

    paths: AtlasPaths = field(default_factory=AtlasPaths)
    ollama_base_url: str = OLLAMA_BASE_URL
    ollama_model: str = OLLAMA_MODEL
    shortlisted_threshold: int = SHORTLIST_THRESHOLD
    maybe_threshold: int = MAYBE_THRESHOLD
    preprocess_workers: int = PREPROCESS_WORKERS
    ollama_timeout_seconds: int = OLLAMA_TIMEOUT_SECONDS
    ollama_max_retries: int = OLLAMA_MAX_RETRIES
    ollama_retry_delays: tuple[int, int] = OLLAMA_RETRY_DELAYS
    ollama_temperature: float = OLLAMA_TEMPERATURE
    ollama_top_p: float = OLLAMA_TOP_P
    ollama_top_k: int = OLLAMA_TOP_K
    ollama_num_ctx: int = OLLAMA_NUM_CTX
    ollama_num_predict: int = OLLAMA_NUM_PREDICT
    ollama_think: bool = OLLAMA_THINK
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS
    ocr_timeout_seconds: int = OCR_TIMEOUT_SECONDS
    ocr_max_retries: int = OCR_MAX_RETRIES
    ocr_retry_delays: tuple[int, int] = OCR_RETRY_DELAYS
    max_resume_excerpt_chars: int = MAX_RESUME_EXCERPT_CHARS
    max_scraped_text_chars: int = MAX_SCRAPED_TEXT_CHARS
    max_links_per_resume: int = MAX_LINKS_PER_RESUME
    max_prompt_chars: int = MAX_PROMPT_CHARS
    max_prompt_estimated_tokens: int = MAX_PROMPT_ESTIMATED_TOKENS
    max_source_summary_chars: int = MAX_SOURCE_SUMMARY_CHARS
    max_debug_artifact_chars: int = MAX_DEBUG_ARTIFACT_CHARS
    network_failure_threshold: int = NETWORK_FAILURE_THRESHOLD
    network_recovery_seconds: int = NETWORK_RECOVERY_SECONDS
    progress_refresh_seconds: float = PROGRESS_REFRESH_SECONDS
    dns_resolvers: tuple[str, ...] = DNS_RESOLVERS

    def ensure_directories(self) -> None:
        """Create the working directories Atlas expects."""

        for path in (
            self.paths.workspace,
            self.paths.incoming,
            self.paths.processing,
            self.paths.shortlisted,
            self.paths.maybe,
            self.paths.rejected,
            self.paths.failed,
            self.paths.reports,
            self.paths.debug,
            self.paths.logs,
            self.paths.docs,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def decision_for_score(self, score: int) -> str:
        """Map a numeric score to a recruiter decision bucket."""

        if score >= self.shortlisted_threshold:
            return "Shortlisted"
        if score >= self.maybe_threshold:
            return "Maybe"
        return "Rejected"


DEFAULT_CONFIG = AtlasConfig()


def build_config(
    *,
    root: Path | str | None = None,
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    reports_dir: Path | str | None = None,
) -> AtlasConfig:
    """Build an AtlasConfig from defaults with optional CLI overrides."""

    paths = AtlasPaths(root=Path(root)) if root is not None else AtlasPaths()
    if reports_dir is not None:
        reports = Path(reports_dir)
        paths = AtlasPaths(
            root=paths.root,
            reports=reports,
            workbook=reports / "Candidates.xlsx",
            checkpoint=reports / "atlas_checkpoint.json",
        )
    return AtlasConfig(
        paths=paths,
        ollama_base_url=ollama_base_url or OLLAMA_BASE_URL,
        ollama_model=ollama_model or OLLAMA_MODEL,
        shortlisted_threshold=SHORTLIST_THRESHOLD,
        maybe_threshold=MAYBE_THRESHOLD,
        preprocess_workers=PREPROCESS_WORKERS,
        ollama_timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
        ollama_max_retries=OLLAMA_MAX_RETRIES,
        ollama_retry_delays=OLLAMA_RETRY_DELAYS,
        ollama_temperature=OLLAMA_TEMPERATURE,
        ollama_top_p=OLLAMA_TOP_P,
        ollama_top_k=OLLAMA_TOP_K,
        ollama_num_ctx=OLLAMA_NUM_CTX,
        ollama_num_predict=OLLAMA_NUM_PREDICT,
        ollama_think=OLLAMA_THINK,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        ocr_timeout_seconds=OCR_TIMEOUT_SECONDS,
        ocr_max_retries=OCR_MAX_RETRIES,
        ocr_retry_delays=OCR_RETRY_DELAYS,
        max_resume_excerpt_chars=MAX_RESUME_EXCERPT_CHARS,
        max_scraped_text_chars=MAX_SCRAPED_TEXT_CHARS,
        max_links_per_resume=MAX_LINKS_PER_RESUME,
        max_prompt_chars=MAX_PROMPT_CHARS,
        max_prompt_estimated_tokens=MAX_PROMPT_ESTIMATED_TOKENS,
        max_source_summary_chars=MAX_SOURCE_SUMMARY_CHARS,
        max_debug_artifact_chars=MAX_DEBUG_ARTIFACT_CHARS,
        network_failure_threshold=NETWORK_FAILURE_THRESHOLD,
        network_recovery_seconds=NETWORK_RECOVERY_SECONDS,
        progress_refresh_seconds=PROGRESS_REFRESH_SECONDS,
        dns_resolvers=DNS_RESOLVERS,
    )
