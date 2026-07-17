"""Model validation tests."""

from __future__ import annotations

import unittest

from models.candidate import CandidateEvaluation, CandidateProfile, ScreeningRecord


class ModelTests(unittest.TestCase):
    def test_evaluation_validation(self) -> None:
        payload = {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "overall_score": 81,
            "technical_score": 88,
            "github_score": 75,
            "projects_score": 84,
            "leadership_score": 60,
            "communication_score": 72,
            "achievements_score": 68,
            "recommendation": "Shortlisted",
            "summary": "Strong fit",
            "strengths": ["Python", "Projects"],
            "weaknesses": ["Limited leadership"],
        }
        evaluation = CandidateEvaluation.model_validate(payload)
        self.assertEqual(evaluation.overall_score, 81)

    def test_profile_validation(self) -> None:
        profile = CandidateProfile(resume_file="resume.pdf")
        self.assertEqual(profile.resume_file, "resume.pdf")

    def test_record_validation(self) -> None:
        record = ScreeningRecord(candidate_name="Jane Doe", overall_score=77)
        self.assertEqual(record.overall_score, 77)


if __name__ == "__main__":
    unittest.main()
