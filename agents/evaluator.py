"""Candidate evaluation logic."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import orjson
from pydantic import ValidationError

from config import AtlasConfig
from llm.ollama import OllamaClient
from llm.prompts import build_evaluation_prompt
from models.candidate import CandidateEvaluation, CandidateProfile, SocialLinks
from parsers.link_extractor import LinkExtractor
from parsers.pdf_parser import PDFParseError
from parsers.pdf_parser import PDFParser
from scrapers.github import GitHubScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.portfolio import PortfolioScraper
from scrapers.common import FetchOutcome, NetworkMonitor, compact_url_summary


EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3}\)?[\s-]?)\d{3}[\s-]?\d{4}")
COLLEGE_PATTERN = re.compile(
    r"(?:college|university|institute of technology|school of engineering)[^\n,.]{0,80}",
    re.IGNORECASE,
)
DEGREE_PATTERN = re.compile(
    r"\b(?:B\.?Tech|B\.?E\.?|Bachelor of Technology|Bachelor of Engineering|M\.?Tech|M\.?S\.?|BSc|MSc|MBA)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvaluationOutcome:
    """Complete evaluation result for a candidate."""

    profile: CandidateProfile
    evaluation: CandidateEvaluation
    timings: dict[str, float]
    prompt: str = ""
    raw_response: dict[str, Any] | None = None
    prompt_stats: dict[str, int] | None = None


class FatalEvaluationError(RuntimeError):
    """Raised when the local LLM cannot produce a valid result after retries."""


class ProfileParseError(RuntimeError):
    """Raised when a PDF cannot be parsed into resume text."""


class CandidateEvaluator:
    """Build candidate profiles and score them using deterministic analysis plus Ollama."""

    def __init__(self, config: AtlasConfig, ollama: OllamaClient, logger: logging.Logger, internet_available: bool, network_monitor: NetworkMonitor | None = None) -> None:
        self.config = config
        self.ollama = ollama
        self.logger = logger
        self.internet_available = internet_available
        self.network_monitor = network_monitor
        self.pdf_parser = PDFParser(config)
        self.link_extractor = LinkExtractor()
        self.github_scraper = GitHubScraper()
        self.linkedin_scraper = LinkedInScraper()
        self.portfolio_scraper = PortfolioScraper()

    def build_profile(self, pdf_path: Path) -> CandidateProfile:
        """Extract text and prepare a compact candidate profile."""

        try:
            extraction = self.pdf_parser.extract_text(pdf_path)
        except PDFParseError as exc:
            raise ProfileParseError(str(exc)) from exc
        text = extraction.text
        excerpt = text[: self.config.max_resume_excerpt_chars]
        links = self.link_extractor.extract(text)[: self.config.max_links_per_resume]
        social_links = self._classify_links(links)
        source_summaries, source_timings = self._scrape_links(social_links)
        deterministic_context = self._deterministic_analysis(text, social_links, source_summaries)
        deterministic_context["pdf_time"] = extraction.pdf_time
        deterministic_context["ocr_time"] = extraction.ocr_time
        deterministic_context["ocr_used"] = extraction.ocr_used
        deterministic_context["ocr_reason"] = extraction.ocr_reason
        deterministic_context["source_timings"] = source_timings
        deterministic_context["source_failures"] = {
            label: value for label, value in source_summaries.items() if value == "Unavailable"
        }
        return CandidateProfile(
            resume_file=str(pdf_path),
            resume_name=pdf_path.name,
            name=self._first_emailless_name(text),
            email=self._find_email(text),
            phone=self._find_phone(text),
            college=self._find_college(text),
            degree=self._find_degree(text),
            summary=deterministic_context["summary"],
            resume_excerpt=excerpt,
            skills=deterministic_context["skills"],
            projects=deterministic_context["projects"],
            achievements=deterministic_context["achievements"],
            leadership_signals=deterministic_context["leadership_signals"],
            communication_signals=deterministic_context["communication_signals"],
            github_signals=deterministic_context["github_signals"],
            deterministic_context=deterministic_context,
            source_summaries=source_summaries,
            links=social_links,
        )

    def evaluate(self, profile: CandidateProfile) -> CandidateEvaluation:
        """Score a candidate using the local model and strict validation."""

        prompt, prompt_stats = self._build_prompt(profile)
        self._log_prompt_stats(profile, prompt_stats, prompt)
        evaluation, _raw_response, _metrics = self._evaluate_profile(profile, prompt, with_metrics=False)
        return evaluation

    def evaluate_path(self, pdf_path: Path) -> EvaluationOutcome:
        """Convenience wrapper used by the pipeline."""

        profile = self.build_profile(pdf_path)
        llm_started = time.perf_counter()
        evaluation = self.evaluate(profile)
        timings = dict(profile.deterministic_context.get("source_timings", {}))
        timings["pdf"] = float(profile.deterministic_context.get("pdf_time", 0.0))
        timings["ocr"] = float(profile.deterministic_context.get("ocr_time", 0.0))
        timings["ocr_used"] = 1.0 if profile.deterministic_context.get("ocr_used") else 0.0
        timings["llm"] = time.perf_counter() - llm_started
        return EvaluationOutcome(profile=profile, evaluation=evaluation, timings=timings)

    def evaluate_path_with_details(self, pdf_path: Path) -> EvaluationOutcome:
        """Convenience wrapper used by debug mode to capture full LLM artifacts."""

        profile = self.build_profile(pdf_path)
        llm_started = time.perf_counter()
        prompt, prompt_stats = self._build_prompt(profile)
        self._log_prompt_stats(profile, prompt_stats, prompt)
        evaluation, raw_response, llm_metrics = self._evaluate_profile(profile, prompt, with_metrics=True)
        timings = dict(profile.deterministic_context.get("source_timings", {}))
        timings["pdf"] = float(profile.deterministic_context.get("pdf_time", 0.0))
        timings["ocr"] = float(profile.deterministic_context.get("ocr_time", 0.0))
        timings["ocr_used"] = 1.0 if profile.deterministic_context.get("ocr_used") else 0.0
        timings["llm"] = llm_metrics.get("total_duration", time.perf_counter() - llm_started)
        return EvaluationOutcome(profile=profile, evaluation=evaluation, timings=timings, prompt=prompt, raw_response=raw_response, prompt_stats=prompt_stats)

    def _evaluate_profile(self, profile: CandidateProfile, prompt: str, with_metrics: bool) -> tuple[CandidateEvaluation, dict[str, Any], dict[str, float]]:
        last_error: Exception | None = None
        for attempt in range(self.config.ollama_max_retries + 1):
            try:
                if with_metrics:
                    raw_response, metrics = self.ollama.evaluate_json_with_metrics(prompt)
                else:
                    raw_response = self.ollama.evaluate_json(prompt)
                    metrics = {}
                evaluation = CandidateEvaluation.model_validate(raw_response)
                enriched = self._align_identifiers(profile, evaluation)
                enriched = self._enrich_scores(profile, enriched)
                return enriched, raw_response, metrics
            except (ValidationError, orjson.JSONDecodeError, ValueError, RuntimeError, Exception) as exc:
                last_error = exc
                if attempt < self.config.ollama_max_retries:
                    self.logger.warning("LLM evaluation failed for %s; retrying (%s/%s).", profile.resume_name, attempt + 2, self.config.ollama_max_retries + 1)
                continue
        raise FatalEvaluationError(f"LLM evaluation failed after {self.config.ollama_max_retries + 1} attempts: {last_error}") from last_error

    def _profile_payload(self, profile: CandidateProfile) -> str:
        return json.dumps(self._prompt_payload(profile), ensure_ascii=False)

    def _prompt_payload(self, profile: CandidateProfile, resume_limit: int | None = None, source_limit: int | None = None) -> dict[str, Any]:
        resume_limit = resume_limit or self.config.max_resume_excerpt_chars
        source_limit = source_limit or self.config.max_source_summary_chars
        source_summaries = {
            label: self._truncate_text(summary, source_limit)
            for label, summary in profile.source_summaries.items()
        }
        payload: dict[str, Any] = {
            "file": profile.resume_name,
            "name": profile.name,
            "email": profile.email,
            "phone": profile.phone,
            "college": profile.college,
            "degree": profile.degree,
            "summary": self._truncate_text(profile.summary, source_limit),
            "excerpt": self._truncate_text(profile.resume_excerpt, resume_limit),
            "skills": profile.skills[:10],
            "projects": profile.projects[:6],
            "achievements": profile.achievements[:6],
            "leadership": profile.leadership_signals[:6],
            "communication": profile.communication_signals[:6],
            "github_signals": profile.github_signals[:6],
            "sources": source_summaries,
            "ocr_used": profile.deterministic_context.get("ocr_used", False),
        }
        return payload

    def _build_prompt(self, profile: CandidateProfile) -> tuple[str, dict[str, int]]:
        resume_limit = self.config.max_resume_excerpt_chars
        source_limit = self.config.max_source_summary_chars
        prompt = ""
        prompt_stats: dict[str, int] = {}
        for _ in range(8):
            prompt_stats = self._prompt_stats(profile, resume_limit, source_limit)
            prompt = build_evaluation_prompt(
                json.dumps(self._prompt_payload(profile, resume_limit=resume_limit, source_limit=source_limit), ensure_ascii=False),
                shortlisted_threshold=self.config.shortlisted_threshold,
                maybe_threshold=self.config.maybe_threshold,
            )
            if len(prompt) <= self.config.max_prompt_chars:
                break
            resume_limit = max(400, resume_limit - 400)
            source_limit = max(200, source_limit - 200)
        return prompt, prompt_stats

    def _prompt_stats(self, profile: CandidateProfile, resume_limit: int, source_limit: int) -> dict[str, int]:
        payload = self._prompt_payload(profile, resume_limit=resume_limit, source_limit=source_limit)
        prompt = build_evaluation_prompt(
            json.dumps(payload, ensure_ascii=False),
            shortlisted_threshold=self.config.shortlisted_threshold,
            maybe_threshold=self.config.maybe_threshold,
        )
        stats = {
            "resume": len(payload.get("excerpt", "")),
            "github": len(payload.get("sources", {}).get("github", "")),
            "linkedin": len(payload.get("sources", {}).get("linkedin", "")),
            "portfolio": len(payload.get("sources", {}).get("portfolio", "")),
            "prompt": len(prompt),
            "tokens": int(round(len(prompt) / 4)),
        }
        return stats

    def _log_prompt_stats(self, profile: CandidateProfile, prompt_stats: dict[str, int], prompt: str) -> None:
        self.logger.info(
            "Prompt stats for %s | resume=%s chars | github=%s chars | linkedin=%s chars | portfolio=%s chars | prompt=%s chars | est_tokens=%s",
            profile.resume_name,
            prompt_stats.get("resume", 0),
            prompt_stats.get("github", 0),
            prompt_stats.get("linkedin", 0),
            prompt_stats.get("portfolio", 0),
            len(prompt),
            min(prompt_stats.get("tokens", 0), self.config.max_prompt_estimated_tokens),
        )

    def _truncate_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + "..."

    def _classify_links(self, links: list[str]) -> SocialLinks:
        github = ""
        linkedin = ""
        portfolio = ""
        others: list[str] = []
        for link in links:
            lower = link.lower()
            if not github and "github.com" in lower:
                github = link
            elif not linkedin and "linkedin.com" in lower:
                linkedin = link
            elif not portfolio:
                portfolio = link
            else:
                others.append(link)
        return SocialLinks(github_url=github, linkedin_url=linkedin, portfolio_url=portfolio, other_urls=others)

    def _scrape_links(self, links: SocialLinks) -> tuple[dict[str, str], dict[str, float]]:
        summaries: dict[str, str] = {}
        failures: dict[str, str] = {}
        timings: dict[str, float] = {"github": 0.0, "linkedin": 0.0, "portfolio": 0.0}
        for label, url in (("github", links.github_url), ("linkedin", links.linkedin_url), ("portfolio", links.portfolio_url)):
            if not url:
                continue
            outcome = self._scrape_single(url)
            timings[label] = outcome.elapsed_seconds
            if outcome.available and outcome.text:
                summaries[label] = compact_url_summary(url) + "\n" + self._truncate_text(outcome.text, self.config.max_scraped_text_chars)
            else:
                summaries[label] = "Unavailable"
                failures[label] = outcome.reason or "Unavailable"
                if self.internet_available:
                    self._log_source_unavailable(label, outcome.reason)
        if failures:
            summaries["failures"] = json.dumps(failures, ensure_ascii=False)
        return summaries, timings

    def _scrape_single(self, url: str) -> FetchOutcome:
        if not self.internet_available:
            return FetchOutcome(url=url, available=False, reason="Internet connection unavailable")
        if self.github_scraper.can_handle(url):
            return self.github_scraper.scrape(url, timeout=self.config.request_timeout_seconds, monitor=self.network_monitor, config=self.config)
        if self.linkedin_scraper.can_handle(url):
            return self.linkedin_scraper.scrape(url, timeout=self.config.request_timeout_seconds, monitor=self.network_monitor, config=self.config)
        if self.portfolio_scraper.can_handle(url):
            return self.portfolio_scraper.scrape(url, timeout=self.config.request_timeout_seconds, monitor=self.network_monitor, config=self.config)
        return FetchOutcome(url=url, available=False, reason="Unsupported URL")

    def _log_source_unavailable(self, label: str, reason: str) -> None:
        message_map = {
            "github": "GitHub profile unavailable",
            "linkedin": "LinkedIn profile unavailable",
            "portfolio": "Portfolio unavailable",
        }
        message = message_map.get(label, f"{label.title()} unavailable")
        if reason:
            self.logger.warning("%s. Reason: %s. Continuing without %s data...", message, reason, label.title())
        else:
            self.logger.warning("%s. Continuing without %s data...", message, label.title())

    def _deterministic_analysis(
        self,
        text: str,
        links: SocialLinks,
        source_summaries: dict[str, str],
    ) -> dict[str, Any]:
        skills = self._extract_skills(text)
        projects = self._extract_project_snippets(text)
        achievements = self._extract_keyword_snippets(text, ["award", "winner", "hackathon", "published", "certified"])
        leadership = self._extract_keyword_snippets(text, ["lead", "captain", "president", "mentor", "organizer", "coordinator"])
        communication = self._extract_keyword_snippets(text, ["presentation", "communication", "public speaking", "writing", "collaboration"])
        github_signals = []
        if links.github_url:
            github_signals.append(links.github_url)
        if "github" in source_summaries:
            github_signals.append(source_summaries["github"])
        summary = self._build_summary(text, skills, projects, achievements)
        return {
            "skills": skills,
            "projects": projects,
            "achievements": achievements,
            "leadership_signals": leadership,
            "communication_signals": communication,
            "github_signals": github_signals,
            "summary": summary,
        }

    def _build_summary(self, text: str, skills: list[str], projects: list[str], achievements: list[str]) -> str:
        first_lines = [line.strip() for line in text.splitlines() if line.strip()][:6]
        fragments = []
        if skills:
            fragments.append(f"skills: {', '.join(skills[:6])}")
        if projects:
            fragments.append(f"projects: {len(projects)} notable references")
        if achievements:
            fragments.append(f"achievements: {len(achievements)} signal(s)")
        if first_lines:
            fragments.append(f"resume preview: {first_lines[0][:160]}")
        return " | ".join(fragments)[:500]

    def _extract_skills(self, text: str) -> list[str]:
        raw_keywords = [
            "python",
            "java",
            "c++",
            "sql",
            "aws",
            "azure",
            "docker",
            "kubernetes",
            "react",
            "node",
            "typescript",
            "javascript",
            "pandas",
            "machine learning",
            "nlp",
            "data analysis",
            "spring boot",
            "fastapi",
        ]
        lower = text.lower()
        found = [keyword for keyword in raw_keywords if keyword in lower]
        return found[:12]

    def _extract_project_snippets(self, text: str) -> list[str]:
        project_lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            if "project" in lower or lower.startswith(("- ", "* ", "• ")):
                project_lines.append(stripped)
        return project_lines[:8]

    def _extract_keyword_snippets(self, text: str, keywords: list[str]) -> list[str]:
        snippets: list[str] = []
        lower = text.lower()
        for keyword in keywords:
            if keyword in lower:
                snippets.append(keyword)
        return snippets

    def _find_email(self, text: str) -> str:
        match = EMAIL_PATTERN.search(text)
        return match.group(0) if match else ""

    def _find_phone(self, text: str) -> str:
        match = PHONE_PATTERN.search(text)
        return match.group(0) if match else ""

    def _find_college(self, text: str) -> str:
        match = COLLEGE_PATTERN.search(text)
        return " ".join(match.group(0).split()) if match else ""

    def _find_degree(self, text: str) -> str:
        match = DEGREE_PATTERN.search(text)
        return match.group(0) if match else ""

    def _first_emailless_name(self, text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        for line in lines[:5]:
            if "@" in line:
                continue
            if len(line.split()) <= 6:
                return line[:80]
        return lines[0][:80]

    def evaluate_with_timing(self, pdf_path: Path) -> EvaluationOutcome:
        """Evaluate a PDF and return the profile, scores, and timing data."""

        return self.evaluate_path(pdf_path)

    def _align_identifiers(self, profile: CandidateProfile, evaluation: CandidateEvaluation) -> CandidateEvaluation:
        data = evaluation.model_dump()
        if not data.get("name"):
            data["name"] = profile.name
        if not data.get("email"):
            data["email"] = profile.email
        return CandidateEvaluation.model_validate(data)

    def _enrich_scores(self, profile: CandidateProfile, evaluation: CandidateEvaluation) -> CandidateEvaluation:
        data = evaluation.model_dump()
        data["skills_score"] = data.get("skills_score") or self._derive_skills_score(profile, evaluation)
        data["experience_score"] = data.get("experience_score") or self._derive_experience_score(profile, evaluation)
        data["resume_quality_score"] = data.get("resume_quality_score") or self._derive_resume_quality_score(profile, evaluation)
        return CandidateEvaluation.model_validate(data)

    def _derive_skills_score(self, profile: CandidateProfile, evaluation: CandidateEvaluation) -> int:
        score = evaluation.technical_score * 0.6 + len(profile.skills) * 5 + len(profile.github_signals) * 3
        return max(0, min(100, int(round(score))))

    def _derive_experience_score(self, profile: CandidateProfile, evaluation: CandidateEvaluation) -> int:
        score = evaluation.projects_score * 0.4 + evaluation.leadership_score * 0.3 + evaluation.achievements_score * 0.3
        return max(0, min(100, int(round(score))))

    def _derive_resume_quality_score(self, profile: CandidateProfile, evaluation: CandidateEvaluation) -> int:
        completeness = sum(1 for value in (profile.name, profile.email, profile.phone, profile.college, profile.degree) if value)
        score = evaluation.communication_score * 0.4 + evaluation.technical_score * 0.4 + completeness * 4
        return max(0, min(100, int(round(score))))
