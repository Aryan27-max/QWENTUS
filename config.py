"""Atlas configuration.

The workspace root is intentionally hardcoded to the requested local path so the
pipeline can operate without extra deployment configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


WORKSPACE_ROOT = Path(r"c:\this is dekstop\atlas")
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3:8b"

SHORTLIST_THRESHOLD = 60
MAYBE_THRESHOLD = 50

PREPROCESS_WORKERS = 6
OLLAMA_TIMEOUT_SECONDS = 180
REQUEST_TIMEOUT_SECONDS = 20
MAX_RESUME_EXCERPT_CHARS = 8000
MAX_SCRAPED_TEXT_CHARS = 2500
MAX_LINKS_PER_RESUME = 5


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
    reports: Path = field(default_factory=lambda: WORKSPACE_ROOT / "workspace" / "Reports")
    logs: Path = field(default_factory=lambda: WORKSPACE_ROOT / "logs")
    docs: Path = field(default_factory=lambda: WORKSPACE_ROOT / "docs")


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
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS
    max_resume_excerpt_chars: int = MAX_RESUME_EXCERPT_CHARS
    max_scraped_text_chars: int = MAX_SCRAPED_TEXT_CHARS
    max_links_per_resume: int = MAX_LINKS_PER_RESUME

    def ensure_directories(self) -> None:
        """Create the working directories Atlas expects."""

        for path in (
            self.paths.workspace,
            self.paths.incoming,
            self.paths.processing,
            self.paths.shortlisted,
            self.paths.maybe,
            self.paths.rejected,
            self.paths.reports,
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
