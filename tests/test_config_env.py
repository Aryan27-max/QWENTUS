"""Tests for environment-driven Atlas configuration."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_env_overrides_model_and_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QWENTUS_OLLAMA_MODEL", "test-model:1b")
    monkeypatch.setenv("QWENTUS_OLLAMA_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("QWENTUS_SHORTLIST_THRESHOLD", "70")
    monkeypatch.setenv("QWENTUS_MAYBE_THRESHOLD", "55")
    monkeypatch.setenv("QWENTUS_PREPROCESS_WORKERS", "2")

    import importlib

    import config as config_module

    importlib.reload(config_module)

    assert config_module.OLLAMA_MODEL == "test-model:1b"
    assert config_module.OLLAMA_BASE_URL == "http://localhost:9999"
    assert config_module.SHORTLIST_THRESHOLD == 70
    assert config_module.MAYBE_THRESHOLD == 55
    assert config_module.PREPROCESS_WORKERS == 2
    assert config_module.DEFAULT_CONFIG.ollama_model == "test-model:1b"

    # Restore module defaults for other tests
    for key in list(os.environ):
        if key.startswith("QWENTUS_"):
            monkeypatch.delenv(key, raising=False)
    importlib.reload(config_module)


def test_build_config_cli_overrides(tmp_path: Path) -> None:
    from config import build_config

    cfg = build_config(root=tmp_path, ollama_model="cli-model", reports_dir=tmp_path / "out")
    assert cfg.paths.root == tmp_path
    assert cfg.ollama_model == "cli-model"
    assert cfg.paths.reports == tmp_path / "out"
    assert cfg.paths.workbook == tmp_path / "out" / "Candidates.xlsx"
