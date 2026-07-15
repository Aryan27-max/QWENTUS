"""Ollama client tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from config import AtlasConfig
from llm.ollama import OllamaClient


class OllamaClientTests(unittest.TestCase):
    def test_health_check_reports_model_availability(self) -> None:
        config = AtlasConfig()
        client = OllamaClient(config)
        response = MagicMock()
        response.json.return_value = {"models": [{"name": "qwen3:8b"}]}
        response.raise_for_status.return_value = None
        client._session.get = MagicMock(return_value=response)

        health = client.health_check()
        self.assertTrue(health.reachable)
        self.assertTrue(health.model_available)

    def test_evaluate_json_parses_payload(self) -> None:
        config = AtlasConfig()
        client = OllamaClient(config)
        response = MagicMock()
        response.json.return_value = {"message": {"content": '{"name":"Jane","email":"jane@example.com","overall_score":70,"technical_score":70,"github_score":70,"projects_score":70,"leadership_score":70,"communication_score":70,"achievements_score":70,"recommendation":"Maybe","summary":"OK","strengths":[],"weaknesses":[]}'}}
        response.raise_for_status.return_value = None
        client._session.post = MagicMock(return_value=response)

        payload = client.evaluate_json("test prompt")
        self.assertEqual(payload["recommendation"], "Maybe")


if __name__ == "__main__":
    unittest.main()
