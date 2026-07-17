# Atlas RC-2 Stabilization Report

## Outcome

The end-to-end pipeline is now functionally working for the two validation resumes in `workspace/Incoming/`. Both resumes are parsed, scored, moved into the correct decision folders, and written to `workspace/Reports/Candidates.xlsx`.

The remaining gap is performance: the current stack still exceeds the requested sub-90-second batch target because the OCR-heavy resume and the local Ollama model are both expensive on this machine.

## Root Causes Found

1. Ollama streaming was being handled as if the final `done` chunk contained the full response body. In reality, the useful JSON was emitted across the streamed chunks and the terminal chunk had empty `content`.
2. The model was also spending its generation budget on thinking / reasoning tokens, which produced empty or incomplete responses before the response boundary was fixed.
3. The prompt and output contract were too large for the local model budget, which pushed the response toward `done_reason: "length"` and increased latency.
4. `--debug-one` was wired to stale object shapes and crashed before writing its artifact files.
5. OCR fallback remained the dominant runtime cost for scanned resumes.

## Fixes Applied

1. Disabled thinking on the Ollama request and kept the JSON-only contract.
2. Switched the Ollama client back to streaming and accumulated streamed `message.content` chunks before parsing JSON.
3. Shortened the prompt payload and prompt instructions to reduce token pressure.
4. Added safer response parsing and logging under `logs/ollama/`.
5. Split the standard evaluation path from the detailed debug path so `--debug-one` can capture prompt, raw LLM response, validated JSON, and timings.
6. Reduced OCR render resolution from 2x to 1.25x to lower fallback cost.

## Validation Results

Unit tests:

- `python -m unittest discover -s tests` passed: 26 tests OK.

Live RC-2 batch run:

- `Aryan Gupta Resume Final.pdf` processed successfully and moved to `Shortlisted`.
- `DEBARPANCHAUDHURI.pdf` processed successfully and moved to `Shortlisted`.
- Workbook updated successfully.

Observed timings from the debug artifact for `DEBARPANCHAUDHURI.pdf`:

- Prompt size: 4953 chars, estimated 1238 tokens.
- OCR: 75.73 seconds.
- LLM: 76.76 seconds.
- Overall debug run time remained well above the 90-second target.

## Remaining Limitation

The pipeline is stable, but the current OCR plus local Ollama model combination is still too slow for the requested sub-90-second end-to-end target on this machine. The next performance step would need either a faster OCR backend, a smaller/faster local model, or a more aggressive reduction in the LLM output contract.

## Files Touched

- `config.py`
- `llm/ollama.py`
- `llm/prompts.py`
- `agents/evaluator.py`
- `parsers/ocr.py`
- `core/pipeline.py`
