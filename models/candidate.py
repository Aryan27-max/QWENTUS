"""Domain models for candidate profiles and scoring results."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Recommendation = Literal["Shortlisted", "Maybe", "Rejected"]


class SocialLinks(BaseModel):
    """Links discovered in a resume or from scraping."""

    model_config = ConfigDict(extra="forbid")

    github_url: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    other_urls: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    """Structured profile built before LLM evaluation."""

    model_config = ConfigDict(extra="forbid")

    resume_file: str
    resume_name: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    college: str = ""
    degree: str = ""
    summary: str = ""
    resume_excerpt: str = ""
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    leadership_signals: list[str] = Field(default_factory=list)
    communication_signals: list[str] = Field(default_factory=list)
    github_signals: list[str] = Field(default_factory=list)
    deterministic_context: dict[str, object] = Field(default_factory=dict)
    source_summaries: dict[str, str] = Field(default_factory=dict)
    links: SocialLinks = Field(default_factory=SocialLinks)


class CandidateEvaluation(BaseModel):
    """Strict JSON payload returned by the LLM."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    email: str = ""
    overall_score: int = Field(ge=0, le=100)
    technical_score: int = Field(ge=0, le=100)
    skills_score: int = Field(default=0, ge=0, le=100)
    github_score: int = Field(ge=0, le=100)
    projects_score: int = Field(ge=0, le=100)
    experience_score: int = Field(default=0, ge=0, le=100)
    leadership_score: int = Field(ge=0, le=100)
    communication_score: int = Field(ge=0, le=100)
    achievements_score: int = Field(ge=0, le=100)
    resume_quality_score: int = Field(default=0, ge=0, le=100)
    recommendation: Recommendation
    summary: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)


class ScreeningRecord(BaseModel):
    """Row data consumed by the Excel exporter."""

    model_config = ConfigDict(extra="forbid")

    rank: int = 0
    candidate_name: str = ""
    email: str = ""
    phone: str = ""
    college: str = ""
    degree: str = ""
    overall_score: int = 0
    technical_score: int = 0
    github_score: int = 0
    skills_score: int = 0
    projects_score: int = 0
    experience_score: int = 0
    leadership_score: int = 0
    communication_score: int = 0
    achievements_score: int = 0
    resume_quality_score: int = 0
    strengths: str = ""
    weaknesses: str = ""
    recommendation: str = ""
    decision: str = ""
    summary: str = ""
    resume_file: str = ""
    github_url: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    processing_time_seconds: float = 0.0


class RunSummary(BaseModel):
    """Top-level run summary."""

    model_config = ConfigDict(extra="forbid")

    processed: int = 0
    shortlisted: int = 0
    maybe: int = 0
    rejected: int = 0
    failed: int = 0
    report_file: str = ""

    def as_log_message(self) -> str:
        return (
            f"processed={self.processed} shortlisted={self.shortlisted} "
            f"maybe={self.maybe} rejected={self.rejected} failed={self.failed} "
            f"report={self.report_file}"
        )
