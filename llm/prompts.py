"""Prompts used by Atlas.

All LLM-facing instructions live here so the system prompt remains isolated.
"""

from __future__ import annotations


def build_evaluation_prompt(profile_payload: str, shortlisted_threshold: int, maybe_threshold: int) -> str:
    """Construct the single JSON-only prompt for the local model."""

    return f"""You are Atlas, an offline resume screening engine.
Return ONLY valid JSON and nothing else.
Do not wrap the response in markdown.
Do not include code fences.
Do not include commentary.

Your job is to score the candidate using the provided structured profile and return this exact JSON shape:
{{
  "name": "",
  "email": "",
  "overall_score": 85,
  "technical_score": 90,
  "github_score": 82,
  "projects_score": 91,
  "leadership_score": 75,
  "communication_score": 88,
  "achievements_score": 80,
  "recommendation": "Shortlisted",
  "summary": "...",
  "strengths": ["..."],
  "weaknesses": ["..."]
}}

Scoring guidance:
- Use integer scores from 0 to 100.
- Use recommendation values exactly from: Shortlisted, Maybe, Rejected.
- If overall_score >= {shortlisted_threshold}, recommendation should be Shortlisted.
- If overall_score >= {maybe_threshold} and < {shortlisted_threshold}, recommendation should be Maybe.
- If overall_score < {maybe_threshold}, recommendation should be Rejected.
- Keep summary concise and recruiter-friendly.
- strengths and weaknesses must be arrays of short strings.
- Treat the profile as the only source of truth.

Candidate profile JSON:
{profile_payload}
"""
