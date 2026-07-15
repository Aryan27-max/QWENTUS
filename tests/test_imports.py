"""Import verification tests."""

from __future__ import annotations

import importlib
import unittest


MODULES = [
    "config",
    "main",
    "agents.evaluator",
    "core.pipeline",
    "core.queue",
    "parsers.pdf_parser",
    "parsers.link_extractor",
    "scrapers.github",
    "scrapers.linkedin",
    "scrapers.portfolio",
    "llm.ollama",
    "llm.prompts",
    "models.candidate",
    "exporters.excel",
    "utils.logger",
]


class ImportTests(unittest.TestCase):
    def test_all_modules_import(self) -> None:
        for module_name in MODULES:
            with self.subTest(module_name=module_name):
                self.assertIsNotNone(importlib.import_module(module_name))


if __name__ == "__main__":
    unittest.main()
