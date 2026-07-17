"""Local Ollama client used by Atlas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
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
        self._log_dir = self.config.paths.logs / "ollama"
        self._log_dir.mkdir(parents=True, exist_ok=True)

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

        payload, _metrics = self.evaluate_json_with_metrics(prompt)
        return payload

    def evaluate_json_with_metrics(self, prompt: str) -> tuple[dict[str, Any], dict[str, float]]:
        """Ask the local model for JSON-only output and return the parsed payload plus latency metrics."""

        request_payload = {
            "model": self.config.ollama_model,
            "stream": True,
            "format": "json",
            "think": self.config.ollama_think,
            "options": {
                "temperature": self.config.ollama_temperature,
                "top_p": self.config.ollama_top_p,
                "top_k": self.config.ollama_top_k,
                "num_ctx": self.config.ollama_num_ctx,
                "num_predict": self.config.ollama_num_predict,
            },
            "messages": [
                {"role": "user", "content": prompt},
            ],
        }
        request_started = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self._write_json_log(f"{request_started}_request.json", request_payload)

        response = self._session.post(
            f"{self.config.ollama_base_url}/api/chat",
            timeout=self.config.ollama_timeout_seconds,
            stream=True,
            json=request_payload,
        )
        response.raise_for_status()
        raw_lines: list[str] = []
        final_payload: dict[str, Any] = {}
        content_parts: list[str] = []
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8", errors="ignore")
            raw_lines.append(str(raw_line))
            try:
                chunk = orjson.loads(raw_line)
            except Exception:
                continue
            final_payload = chunk
            message = chunk.get("message", {})
            chunk_content = message.get("content", "")
            if isinstance(chunk_content, str) and chunk_content:
                content_parts.append(chunk_content)
            if chunk.get("done"):
                break
        self._write_text_log(f"{request_started}_raw_response.ndjson", "\n".join(raw_lines))
        if not final_payload:
            try:
                final_payload = response.json()
            except Exception as exc:
                self._write_text_log(f"{request_started}_error.txt", str(exc))
                raise
        message = final_payload.get("message", {})
        content = "".join(content_parts)
        if not content:
            content = message.get("content", "")
        if not content and isinstance(message.get("thinking"), str):
            content = message.get("thinking", "")
        metrics = {
            "eval_count": float(final_payload.get("eval_count", 0) or 0),
            "eval_duration": float(final_payload.get("eval_duration", 0) or 0) / 1_000_000_000,
            "prompt_eval_count": float(final_payload.get("prompt_eval_count", 0) or 0),
            "prompt_eval_duration": float(final_payload.get("prompt_eval_duration", 0) or 0) / 1_000_000_000,
            "total_duration": float(final_payload.get("total_duration", 0) or 0) / 1_000_000_000,
        }
        if not isinstance(content, str) or not content.strip():
            content = str(final_payload.get("response", ""))
        if not content:
            raise ValueError("Ollama returned an empty response.")
        parsed = self._parse_json_payload(content)
        self._write_json_log(f"{request_started}_parsed_response.json", parsed)
        self._write_json_log(f"{request_started}_timings.json", metrics)
        return parsed, metrics

    def _write_json_log(self, filename: str, payload: Any) -> None:
        path = self._log_dir / filename
        path.write_text(orjson.dumps(payload, option=orjson.OPT_INDENT_2).decode("utf-8"), encoding="utf-8")

    def _write_text_log(self, filename: str, text: str) -> None:
        path = self._log_dir / filename
        path.write_text(text, encoding="utf-8")

    def _parse_json_payload(self, content: str) -> dict[str, Any]:
        try:
            return orjson.loads(content)
        except Exception:
            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                cleaned = cleaned.removeprefix("json").strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                candidate = cleaned[start : end + 1]
                try:
                    return orjson.loads(candidate)
                except Exception:
                    pass
            raise
