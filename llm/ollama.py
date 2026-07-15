"""Local Ollama client used by Atlas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import orjson
import requests

from config import AtlasConfig


@dataclass(frozen=True)
class OllamaHealth:
    """Minimal health check result for Ollama."""

    reachable: bool
    model_available: bool


class OllamaClient:
    """Thin HTTP client for the local Ollama service."""

    def __init__(self, config: AtlasConfig) -> None:
        self.config = config
        self._session = requests.Session()

    def health_check(self) -> OllamaHealth:
        """Verify that Ollama is reachable and the requested model exists."""

        try:
            response = self._session.get(
                f"{self.config.ollama_base_url}/api/tags",
                timeout=self.config.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return OllamaHealth(reachable=False, model_available=False)

        models = [model.get("name", "") for model in payload.get("models", [])]
        return OllamaHealth(reachable=True, model_available=self.config.ollama_model in models)

    def ensure_ready(self) -> None:
        """Exit early if Ollama or the target model is not available."""

        health = self.health_check()
        if not health.reachable:
            raise RuntimeError("Ollama is not reachable on the local HTTP API.")
        if not health.model_available:
            raise RuntimeError(f'Ollama model "{self.config.ollama_model}" is not available.')

    def evaluate_json(self, prompt: str) -> dict[str, Any]:
        """Ask the local model for JSON-only output and return the parsed payload."""

        response = self._session.post(
            f"{self.config.ollama_base_url}/api/chat",
            timeout=self.config.ollama_timeout_seconds,
            json={
                "model": self.config.ollama_model,
                "stream": False,
                "options": {"temperature": 0.2},
                "messages": [
                    {"role": "user", "content": prompt},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
        message = payload.get("message", {})
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty response.")
        return orjson.loads(content)
