# Atlas Implementation

## Module Overview

`config.py` centralizes the hardcoded workspace path, threshold values, Ollama configuration, and filesystem locations.

`main.py` is the command-line entry point. It creates the logger, verifies the environment, and launches the pipeline.

`parsers/pdf_parser.py` extracts text from PDF files with PyMuPDF.

`parsers/link_extractor.py` detects URLs inside the resume text.

`scrapers/github.py`, `scrapers/linkedin.py`, and `scrapers/portfolio.py` fetch public pages referenced by the resume and compress them into short context strings.

`agents/evaluator.py` builds the candidate profile, performs deterministic feature extraction, and either validates the Ollama response or falls back to a deterministic score model if the JSON cannot be trusted.

`llm/prompts.py` contains the only prompt text used by the model. The prompt demands JSON-only output.

`llm/ollama.py` communicates with the local Ollama HTTP API and verifies that `qwen3:8b` is available before processing.

`exporters/excel.py` writes a recruiter-friendly workbook with a summary sheet and candidate details.

`core/pipeline.py` orchestrates the processing flow, keeps the model calls sequential, parallelizes preprocessing, logs every step, and moves PDFs into the correct destination folder.

`core/queue.py` provides a simple thread-safe queue abstraction for watch mode.

`models/candidate.py` defines the Pydantic models used across the system.

`utils/logger.py` configures file and console logging with timestamps.

## Architecture Diagram

```mermaid
flowchart LR
    A[Incoming PDFs] --> B[PDF Parsing]
    B --> C[Text Extraction]
    C --> D[Email / Phone / Link Extraction]
    D --> E[Website Scraping]
    E --> F[Candidate Profile Builder]
    F --> G[Deterministic Analysis]
    G --> H[Qwen3 Evaluation via Ollama]
    H --> I[JSON Validation]
    I --> J[Excel Generation]
    I --> K[Move PDF]
    J --> L[Reports]
    K --> M[Finished]
```

## Class Diagram

```mermaid
classDiagram
    class AtlasPipeline {
        +run_once() RunSummary
        -_process_pdf(Path)
        -_to_record(EvaluationOutcome)
        -_move_pdf(Path, Path)
    }

    class CandidateEvaluator {
        +build_profile(Path) CandidateProfile
        +evaluate(CandidateProfile) CandidateEvaluation
        +evaluate_path(Path) EvaluationOutcome
    }

    class OllamaClient {
        +ensure_ready()
        +evaluate_json(str) dict
        +health_check() OllamaHealth
    }

    class ExcelExporter {
        +export(list~ScreeningRecord~) Path
    }

    AtlasPipeline --> CandidateEvaluator
    AtlasPipeline --> OllamaClient
    AtlasPipeline --> ExcelExporter
```

## Execution Flow

1. Discover PDFs in `workspace/Incoming`.
2. Extract text and links from each file.
3. Scrape public URLs when they are present.
4. Build a compact candidate profile.
5. Apply deterministic feature extraction.
6. Send one profile at a time to the local Ollama model.
7. Validate the returned JSON against the strict Pydantic model.
8. Export the workbook.
9. Move the PDF into the destination folder.
