"""Prompts used by Atlas.

All LLM-facing instructions live here so the system prompt remains isolated.
"""

from __future__ import annotations


def build_evaluation_prompt(profile_payload: str, shortlisted_threshold: int, maybe_threshold: int) -> str:
    """Construct the single JSON-only prompt for the local model."""

    return f"""You are Atlas.
Return only valid JSON.
No markdown, no code fences, no commentary.

Output a JSON object with exactly these keys:
name, email, overall_score, technical_score, skills_score, github_score, projects_score, experience_score, leadership_score, communication_score, achievements_score, resume_quality_score, recommendation, summary, strengths, weaknesses.

Rules:
- Scores are integers from 0 to 100.
- recommendation must be Shortlisted, Maybe, or Rejected.
- recommendation is Shortlisted if overall_score >= {shortlisted_threshold}.
- recommendation is Maybe if overall_score >= {maybe_threshold} and < {shortlisted_threshold}.
- recommendation is Rejected if overall_score < {maybe_threshold}.
- Keep summary short.
- strengths and weaknesses must be short arrays.

Profile:
{profile_payload}
"""
