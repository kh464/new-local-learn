# GitHub Tech Doc Generator MVP Design

## Overview

This document defines the approved MVP design for a backend-first system that analyzes public GitHub repositories and generates structured technical documentation plus beginner-friendly learning guidance.

The MVP focuses on:

- Public GitHub repositories only
- FastAPI backend APIs
- Redis-backed task state
- ARQ worker execution
- Deterministic repository analysis
- Markdown output
- SSE progress streaming

The MVP explicitly does not include:

- Private repository access
- PDF or HTML export
- Full multi-agent orchestration
- Advanced DAG-based task execution
- Rich frontend UI

## Scope

The original proposal spans multiple subsystems. For the first implementation cycle, the scope is intentionally reduced to a single deliverable:

`GitHub URL -> fetch repository -> run deterministic analysis -> generate structured Markdown documentation -> expose status/result APIs`

This scope is large enough to validate the product direction while keeping architecture, testing, and operational complexity under control.

## Architecture

The MVP is organized into four layers:

### 1. API Gateway

Responsible for:

- Accepting analysis requests
- Creating task identifiers
- Returning task URLs
- Exposing task status
- Returning final analysis results
- Streaming task progress through SSE

This layer should contain no repository analysis logic.

### 2. Task Worker

Responsible for:

- Receiving queued jobs from ARQ
- Executing the analysis pipeline off the request thread
- Updating task progress and stage transitions
- Persisting structured results and generated documents

This layer is the execution boundary for long-running work.

### 3. Analysis Services

Responsible for:

- Repository fetching
- File tree scanning
- Technology stack detection
- Backend analysis
- Frontend analysis
- Logic summary generation
- Beginner-oriented tutorial composition
- Markdown assembly

Each analysis service should expose a narrow, deterministic interface and return structured data rather than free-form text.

### 4. Persistence

Responsible for:

- Storing task status and lightweight metadata in Redis
- Storing repository snapshots, intermediate artifacts, and final Markdown files on local disk

Redis is used for state and coordination. File content and large artifacts are stored on disk under a dedicated artifacts directory.

## Runtime Flow

The approved end-to-end flow is:

1. Client calls `POST /api/v1/analyze` with a public GitHub repository URL.
2. API validates the request, creates a `task_id`, stores initial task status in Redis, and enqueues an ARQ job.
3. ARQ worker fetches the repository into a local workspace.
4. Worker scans the repository tree and extracts key file metadata.
5. Worker detects stack characteristics from common config and source files.
6. Worker runs backend and frontend analyzers when applicable.
7. Worker compiles a structured result object and generates a Markdown document.
8. Worker stores result metadata in Redis and writes artifacts to disk.
9. Client polls status and result endpoints or subscribes to SSE progress updates.

## Project Structure

The MVP codebase should be organized as follows:

- `app/main.py`
  FastAPI application entrypoint and lifespan wiring.
- `app/api/routes/`
  Request/response endpoints only.
- `app/core/config.py`
  Centralized configuration loading.
- `app/core/models.py`
  Shared data models and enums.
- `app/services/repo/`
  Repository fetch and tree scan services.
- `app/services/analyzers/`
  Stack detector, backend analyzer, frontend analyzer, logic mapper, tutor composer.
- `app/services/docs/`
  Markdown and Mermaid generation services.
- `app/tasks/worker.py`
  ARQ worker configuration and task entrypoints.
- `app/storage/`
  Redis access, artifact persistence, and path helpers.
- `tests/`
  Unit, service, task, and API tests.
- `artifacts/`
  Local workspace for cloned repos, JSON artifacts, and generated Markdown output.

## Data Model Design

### Request Model

`AnalyzeRequest`

- `github_url: str`

The MVP accepts only a public GitHub repository URL as input.

### Task State Model

`TaskStatus`

- `task_id: str`
- `state: queued | running | succeeded | failed | cancelled`
- `stage: str | null`
- `progress: int`
- `message: str | null`
- `error: str | null`
- `created_at: datetime`
- `updated_at: datetime`

`cancelled` is reserved for future expansion and is not exposed by the MVP API.

### Stage Model

While `state=running`, `stage` should be one of:

- `fetch_repo`
- `scan_tree`
- `detect_stack`
- `analyze_backend`
- `analyze_frontend`
- `build_doc`
- `finalize`

### Result Model

`AnalysisResult`

- `task_id: str`
- `source: dict`
- `repo_summary: dict`
- `detected_stack: dict`
- `backend_summary: dict | null`
- `frontend_summary: dict | null`
- `logic_summary: dict`
- `tutorial_summary: dict`
- `artifacts: dict`
- `markdown_path: str`

This object must support both JSON API output and Markdown document generation.

### Failure Model

Failure details must preserve:

- `failed_stage`
- `error_code`
- `error_message`
- `retryable`
- `debug_hint`

The MVP should distinguish request validation failures from execution-time analysis failures.

## Redis Design

Each task should use these Redis records:

- `task:{task_id}:status`
  Current task state, stage, progress, timestamps, and error summary.
- `task:{task_id}:meta`
  Input URL, normalized repository identity, working paths, and basic task metadata.
- `task:{task_id}:log`
  Progress event channel for SSE.
- `task:{task_id}:result`
  Lightweight result summary and artifact paths.
- `task:{task_id}:artifact_index`
  References to generated intermediate files such as tree summaries and analyzer outputs.

Redis should store only compact JSON metadata and references. Large files must remain on disk.

## API Design

### `POST /api/v1/analyze`

Creates a new task from a public GitHub repository URL.

Response body:

- `task_id`
- `state`
- `status_url`
- `result_url`
- `stream_url`

Validation rules:

- Invalid or unsupported URLs return `422`.
- Only allowed GitHub hosts are accepted.

### `GET /api/v1/status/{task_id}`

Returns:

- `task_id`
- `state`
- `stage`
- `progress`
- `message`
- `error`
- `updated_at`

### `GET /api/v1/result/{task_id}`

Behavior:

- If complete and successful, return `AnalysisResult`
- If failed, return failure payload
- If still running, return `202 Accepted`

### `GET /api/v1/stream/{task_id}`

Streams SSE events for task progress.

Supported event types:

- `status_changed`
- `stage_started`
- `stage_finished`
- `log`
- `error`
- `completed`

Each event should include:

- `task_id`
- `timestamp`
- `state`
- `stage`
- `message`

## Execution Pipeline

The MVP worker pipeline is strictly linear:

1. `fetch_repo`
2. `scan_tree`
3. `detect_stack`
4. `analyze_backend`
5. `analyze_frontend`
6. `build_doc`
7. `finalize`

This is intentionally simpler than a DAG-based orchestration model and is sufficient for the first release.

Rules:

- If a backend or frontend analyzer is not applicable, record that explicitly instead of failing the task.
- If an optional analyzer fails but the document can still be produced, degrade gracefully and mark the missing data clearly.
- If final document generation fails, mark the whole task as failed because the document is the primary deliverable.

## Analyzer Design

The MVP uses deterministic services rather than true agent-based analysis.

### RepositoryScanner

Responsibilities:

- Traverse the repository tree
- Ignore large or irrelevant directories such as `.git`, `node_modules`, and cache folders
- Produce a repository map and key file list

### StackDetector

Responsibilities:

- Detect languages and frameworks from files such as `package.json`, `pyproject.toml`, `requirements.txt`, and deployment configs
- Identify package manager, frontend framework, backend framework, and deployment hints

### BackendAnalyzer

MVP focus is Python and FastAPI.

Responsibilities:

- Locate FastAPI app entrypoints
- Extract `APIRouter` and route decorators
- Record HTTP methods, paths, handler names, and source files
- Identify common dependency injection and middleware patterns
- Detect model and ORM hints where possible

Non-Python backends may be identified at a high level but are not deeply analyzed in this MVP.

### FrontendAnalyzer

Responsibilities:

- Detect frameworks such as React and Vue
- Identify likely routing and state management libraries
- Scan for API call sites such as `fetch`, `axios`, `useQuery`, and `swr`
- Summarize likely entry components and frontend architecture

The MVP does not attempt a full semantic component graph reconstruction.

### LogicMapper

Responsibilities:

- Produce a best-effort summary of likely end-to-end request flows
- Match frontend API call hints to backend route patterns when evidence is reasonable
- Explicitly label inferred relationships as inferred when proof is incomplete

### TutorComposer

Responsibilities:

- Produce a beginner-friendly system analogy
- Generate run instructions based on detected stack
- Explain one or more core request paths in accessible language
- Generate a small set of common pitfalls and self-check questions

### MermaidBuilder

Responsibilities:

- Generate a system architecture diagram
- Generate a core sequence diagram when enough structure exists

This service should only render diagrams from existing structured results and must not invent code-level facts.

### MarkdownCompiler

Responsibilities:

- Assemble all sections into one final Markdown document
- Include confidence notes and uncovered areas
- Keep section ordering stable and machine-testable

## Output Document Structure

The generated Markdown document should contain these sections:

1. Project Overview
2. Detected Tech Stack
3. Directory and Key Files
4. Backend Analysis
5. Frontend Analysis
6. Core Logic Flows
7. Beginner Learning Guide
8. Appendix and Confidence Notes

The final section must explicitly separate:

- Directly observed facts
- Pattern-based inferences
- Areas not covered or not detected

## Testing Strategy

Implementation should follow TDD.

The MVP test layers are:

### 1. Model and Pure Function Tests

Validate:

- State transitions
- Result schema construction
- Artifact path helpers
- Markdown section assembly

### 2. Analyzer Unit Tests

Use fixture repositories or reduced fixture directories to validate:

- Stack detection
- FastAPI route extraction
- Frontend framework identification
- API call site scanning

### 3. Task Flow Tests

Validate:

- Queue-to-worker state progression
- Stage transitions
- Redis updates
- Artifact persistence
- Failure path behavior

### 4. API Integration Tests

Validate:

- Analyze endpoint behavior
- Status endpoint behavior
- Result endpoint behavior
- SSE streaming behavior

The MVP does not require live GitHub network integration tests. The repository fetch layer should be testable via replaceable adapters or local fixtures.

## Configuration

At minimum, the system should provide these configuration values:

- `REDIS_URL`
- `ARTIFACTS_DIR`
- `WORKSPACE_DIR`
- `MAX_REPO_SIZE_MB`
- `MAX_FILE_COUNT`
- `MAX_FILE_BYTES`
- `ALLOWED_GITHUB_HOSTS`
- `CACHE_TTL_SECONDS`

These limits must not be hard-coded into implementation logic.

## Non-Functional Constraints

The MVP must satisfy these constraints:

- Only public GitHub repositories are supported
- Repository size and scan depth must be limited through configuration
- Per-file read limits must be enforced
- Redis should not store large document content
- Artifacts should be written to local disk in a predictable structure
- Analyzer failures should degrade gracefully where possible
- Inferred content must always be labeled as inferred

## Out of Scope

The following items are intentionally excluded from the MVP:

- Private repository support and GitHub token handling
- PDF and HTML export
- True multi-agent orchestration
- Complex DAG execution
- Rich UI beyond API consumption
- User accounts or persistent task history database
- Task cancellation endpoint
- Deep semantic business understanding across large codebases

## Recommended Implementation Direction

The recommended implementation direction is:

- FastAPI for the API server
- Redis for task state and progress event coordination
- ARQ for background job execution
- Deterministic analyzers for repository understanding
- Markdown as the only first-phase document format

This preserves a clean path toward future LLM-assisted analyzers and richer outputs without overloading the first implementation cycle.

## Risks and Mitigations

### Risk: Large repositories exceed practical scan limits

Mitigation:

- Apply configurable file count and file size limits
- Use repository map summaries before deeper scans
- Explicitly mark skipped areas in the output

### Risk: Cross-framework detection produces false confidence

Mitigation:

- Keep detections rule-based and transparent
- Attach confidence notes to generated sections
- Avoid claiming semantic certainty without strong evidence

### Risk: Analyzer failures reduce output quality

Mitigation:

- Isolate analyzers behind narrow interfaces
- Allow partial degradation when document generation can continue
- Preserve failure details for debugging

### Risk: Operational complexity grows too early

Mitigation:

- Keep the first worker pipeline linear
- Avoid premature agent orchestration
- Restrict the first deliverable to backend APIs and Markdown output

## Approval Record

Approved interactively in this session:

- MVP scope instead of the full original platform
- Public GitHub repositories only
- Complete structured output including diagrams and beginner guidance
- Deterministic analysis first, with LLM use deferred
- FastAPI + Redis + ARQ runtime shape
- Backend-first implementation with no rich frontend in phase one

## Implementation Readiness

This design is approved for conversion into an implementation plan. The next step is to create a task-by-task implementation plan before touching production code.
