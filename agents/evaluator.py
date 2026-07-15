"""Candidate evaluation logic."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import AtlasConfig
from llm.ollama import OllamaClient
from llm.prompts import build_evaluation_prompt
from models.candidate import CandidateEvaluation, CandidateProfile, SocialLinks
from parsers.link_extractor import LinkExtractor
from parsers.pdf_parser import PDFParser
from scrapers.github import GitHubScraper
from scrapers.linkedin import LinkedInScraper
from scrapers.portfolio import PortfolioScraper


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


class CandidateEvaluator:
    """Build candidate profiles and score them using deterministic analysis plus Ollama."""

    def __init__(self, config: AtlasConfig, ollama: OllamaClient) -> None:
        self.config = config
        self.ollama = ollama
        self.pdf_parser = PDFParser()
        self.link_extractor = LinkExtractor()
        self.github_scraper = GitHubScraper()
        self.linkedin_scraper = LinkedInScraper()
        self.portfolio_scraper = PortfolioScraper()

    def build_profile(self, pdf_path: Path) -> CandidateProfile:
        """Extract text and prepare a compact candidate profile."""

        text = self.pdf_parser.extract_text(pdf_path)
        excerpt = text[: self.config.max_resume_excerpt_chars]
        links = self.link_extractor.extract(text)[: self.config.max_links_per_resume]
        social_links = self._classify_links(links)
        source_summaries = self._scrape_links(social_links)
        deterministic_context = self._deterministic_analysis(text, social_links, source_summaries)
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

        prompt = build_evaluation_prompt(
            self._profile_payload(profile),
            shortlisted_threshold=self.config.shortlisted_threshold,
            maybe_threshold=self.config.maybe_threshold,
        )
        try:
            raw = self.ollama.evaluate_json(prompt)
            evaluation = CandidateEvaluation.model_validate(raw)
        except Exception:
            evaluation = self._fallback_evaluation(profile)
        return self._align_identifiers(profile, evaluation)

    def evaluate_path(self, pdf_path: Path) -> EvaluationOutcome:
        """Convenience wrapper used by the pipeline."""

        profile = self.build_profile(pdf_path)
        evaluation = self.evaluate(profile)
        return EvaluationOutcome(profile=profile, evaluation=evaluation)

    def _profile_payload(self, profile: CandidateProfile) -> str:
        return json.dumps(profile.model_dump(), ensure_ascii=False)

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

    def _scrape_links(self, links: SocialLinks) -> dict[str, str]:
        summaries: dict[str, str] = {}
        for label, url in (("github", links.github_url), ("linkedin", links.linkedin_url), ("portfolio", links.portfolio_url)):
            if not url:
                continue
            summary = self._scrape_single(url)
            if summary:
                summaries[label] = summary[: self.config.max_scraped_text_chars]
        return summaries

    def _scrape_single(self, url: str) -> str:
        if self.github_scraper.can_handle(url):
            return self.github_scraper.scrape(url, timeout=self.config.request_timeout_seconds)
        if self.linkedin_scraper.can_handle(url):
            return self.linkedin_scraper.scrape(url, timeout=self.config.request_timeout_seconds)
        if self.portfolio_scraper.can_handle(url):
            return self.portfolio_scraper.scrape(url, timeout=self.config.request_timeout_seconds)
        return ""

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

    def _fallback_evaluation(self, profile: CandidateProfile) -> CandidateEvaluation:
        technical = self._score_technical(profile)
        github = self._score_github(profile)
        projects = self._score_projects(profile)
        leadership = self._score_signal_count(profile.leadership_signals)
        communication = self._score_signal_count(profile.communication_signals)
        achievements = self._score_signal_count(profile.achievements)
        overall = round(
            technical * 0.35
            + github * 0.15
            + projects * 0.20
            + leadership * 0.10
            + communication * 0.10
            + achievements * 0.10
        )
        recommendation = self._recommendation_from_score(overall)
        return CandidateEvaluation(
            name=profile.name,
            email=profile.email,
            overall_score=overall,
            technical_score=technical,
            github_score=github,
            projects_score=projects,
            leadership_score=leadership,
            communication_score=communication,
            achievements_score=achievements,
            recommendation=recommendation,
            summary=profile.summary or "Fallback deterministic evaluation generated because the local model response could not be validated.",
            strengths=profile.skills[:5] or ["Baseline technical profile detected"],
            weaknesses=["Model output required fallback validation"],
        )

    def _recommendation_from_score(self, score: int) -> str:
        if score >= self.config.shortlisted_threshold:
            return "Shortlisted"
        if score >= self.config.maybe_threshold:
            return "Maybe"
        return "Rejected"

    def _score_technical(self, profile: CandidateProfile) -> int:
        score = 20
        score += min(len(profile.skills) * 8, 40)
        score += min(len(profile.projects) * 5, 20)
        score += 10 if profile.degree else 0
        score += 10 if profile.college else 0
        score += 10 if profile.resume_excerpt else 0
        return min(score, 100)

    def _score_github(self, profile: CandidateProfile) -> int:
        score = 0
        if profile.links.github_url:
            score += 40
        score += min(len(profile.github_signals) * 15, 30)
        if "github" in profile.source_summaries:
            score += 20
        return min(score + 10, 100)

    def _score_projects(self, profile: CandidateProfile) -> int:
        score = min(len(profile.projects) * 12, 60)
        if any("project" in item.lower() for item in profile.projects):
            score += 20
        return min(score + 10, 100)

    def _score_signal_count(self, signals: list[str]) -> int:
        return min(30 + len(signals) * 20, 100)

    def _align_identifiers(self, profile: CandidateProfile, evaluation: CandidateEvaluation) -> CandidateEvaluation:
        data = evaluation.model_dump()
        if not data.get("name"):
            data["name"] = profile.name
        if not data.get("email"):
            data["email"] = profile.email
        return CandidateEvaluation.model_validate(data)
