# Prompt and Threshold Paths

This file lists the places where Atlas prompt text and candidate thresholds are defined.

## Basic prompt text

- [llm/prompts.py](llm/prompts.py)
  - Contains the user-facing scoring prompt template sent to Ollama.
- [agents/evaluator.py](agents/evaluator.py)
  - Builds the final prompt payload and trims the resume/source text before sending it to the model.

## Thresholds

- [config.py](config.py)
  - Defines `SHORTLIST_THRESHOLD` and `MAYBE_THRESHOLD`.
  - Also exposes them on `AtlasConfig.shortlisted_threshold` and `AtlasConfig.maybe_threshold`.
- [llm/prompts.py](llm/prompts.py)
  - Injects the threshold values into the prompt instructions.
- [agents/evaluator.py](agents/evaluator.py)
  - Uses the thresholds when building the prompt and when enriching scores.
