# Atlas Testing Report

This report records the validation run completed against the local virtual environment.

## Executed tests

- `python -m unittest discover -s tests -v`
- Import verification for all project modules
- PDF parsing and link extraction tests
- Candidate model validation tests
- Ollama client JSON parsing and health-check tests
- Excel generation test
- Pipeline movement and report creation test
- Logging file creation test
- Live Ollama connectivity check using `OllamaClient.health_check()`
- End-to-end startup run with `python main.py` against an empty Incoming folder and no internet connectivity
- Scraper resilience tests for broken GitHub URLs, deleted accounts, invalid URLs, SSL failures, timeouts, connection resets, LinkedIn failure, Portfolio failure, successful scrape, and offline detection
- Pipeline resilience test covering broken external links plus a corrupted PDF routed into `workspace/Failed`
- Pipeline resilience tests covering repeated LLM failure and repeated JSON validation failure routed into `workspace/Failed`

## Expected output

- All tests pass, generated workbook exists, processed PDF is moved into the shortlist bucket, external scraping failures remain non-fatal, and fatal PDFs are routed into `workspace/Failed`.

## Actual output

- 26 tests executed successfully.
- The workbook was generated at `workspace/Reports/atlas_screening_report.xlsx` during the pipeline test.
- The sample PDF was moved into `workspace/Shortlisted`.
- The logging test confirmed `atlas.log` creation after handler cleanup.
- Ollama health check returned `reachable=True, model_available=True`.
- `python main.py` exited cleanly with `processed=0` because there were no PDFs in Incoming.
- Startup emitted one concise offline warning, then continued without scraping and exited normally.
- The resilience batch verified that a corrupted PDF was moved into `workspace/Failed` while a resume with broken external URLs still completed successfully.
- The fatal evaluation tests verified that repeated LLM failure and repeated JSON validation failure both moved the resume into `workspace/Failed`.

## Fixes performed

- Fixed Windows temporary-directory cleanup in the logging test by explicitly flushing, closing, and removing handlers before teardown.
- Added a blocking queue read path for watch mode so new PDFs can be processed continuously.
- Added retry-aware scraping helpers with concise warning output and full stack traces preserved in the log file.
- Added internet connectivity detection so Atlas skips external scraping when the network is unavailable.
- Added fatal resume routing into `workspace/Failed` for corrupted PDFs and repeated evaluation failures.

## Coverage summary

- Module imports, PDF parsing, link extraction, model validation, Ollama client behavior, Excel export, logging, pipeline movement, live Ollama connectivity, startup behavior, scraper failure handling, offline detection, and fatal-folder routing were covered by the validation run.
