# new-local-learn

`new-local-learn` is the repository root for a GitHub technical document generator. The current tracked codebase is a Python backend service that accepts a GitHub repository URL, enqueues an asynchronous ARQ analysis job, clones the target repository, and produces Markdown, HTML, and PDF reports with stack detection, route summaries, logic mapping, deploy notes, critique notes, and Mermaid diagrams.

## What This Repository Contains

- FastAPI API for task submission and result retrieval
- Redis-backed task state storage
- ARQ worker pipeline for repository analysis
- Repository scanning, stack detection, backend/frontend analysis, and tutorial composition
- DAG-style execution tracking for analysis nodes, including fallback metadata in the final result
- Markdown, HTML, PDF, and Mermaid report generation
- Automated tests for API, pipeline, storage, and analyzers

## Current Scope

This root repository currently tracks the backend service.

There is also a local `vue-frontend-workbench/` directory in the workspace, but it is a separate Git worktree/repository and is intentionally not included in this root repository push.

## Architecture Overview

1. Client submits a GitHub repository URL to `POST /api/v1/analyze`.
2. The backend creates a queued task, persists initial state in Redis, and enqueues an ARQ job.
3. The worker clones and scans the target repository.
4. Analyzer services detect frameworks/languages, summarize backend and frontend behavior, and map cross-layer flows.
5. The document compiler emits Markdown, HTML, and PDF reports plus Mermaid diagram content under `artifacts/`.

## Repository Layout

```text
app/
  api/routes/          FastAPI endpoints
  core/                settings and Pydantic models
  services/analyzers/  stack, backend, frontend, and logic analysis
  services/docs/       Markdown and Mermaid generation
  services/repo/       repository normalization and scanning
  storage/             task/result persistence and artifact paths
  tasks/               ARQ worker and analysis job orchestration
tests/                 API, unit, and pipeline tests
docs/                  design notes and implementation planning docs
docker-compose.yml     local API, worker, and Redis stack
pyproject.toml         Python package metadata and dev dependencies
```

## Requirements

- Python 3.12+
- Docker Desktop or another Docker runtime

## Local Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Configuration

The application reads runtime settings from environment variables and `.env`.
Copy `.env.example` to `.env` and edit it for your environment when using Docker Compose.

Available settings in code today:

- `REDIS_URL` default: `redis://localhost:6379/0`
- `ARTIFACTS_DIR` default: `artifacts`
- `WORKSPACE_DIR` default: `artifacts/workspace`
- `MAX_FILE_COUNT` default: `2000`
- `MAX_FILE_BYTES` default: `50000`
- `MAX_TOTAL_BYTES` default: `2000000`
- `ALLOWED_GITHUB_HOSTS` default: `github.com,www.github.com`
- `CORS_ALLOWED_ORIGINS` default: empty
- `API_KEYS` default: empty
- `API_KEY_RECORDS` default: empty
- `CLONE_TIMEOUT_SECONDS` default: `60`
- `STREAM_POLL_INTERVAL_SECONDS` default: `0.1`
- `WORKER_JOB_TIMEOUT_SECONDS` default: `300`
- `WORKER_MAX_JOBS` default: `10`
- `RATE_LIMIT_WINDOW_SECONDS` default: `60`
- `RATE_LIMIT_MAX_REQUESTS` default: `10`
- `AUDIT_MAX_EVENTS` default: `1000`
- `TASK_TTL_SECONDS` default: `86400`
- `ARTIFACT_TTL_SECONDS` default: `86400`
- `REQUEST_LOG_ENABLED` default: `true`
- `LOG_LEVEL` default: `INFO`
- `LLM_ENABLED` default: `true`
- `LLM_CONFIG_PATH` default: `config/llm.yaml`
- `LLM_PROFILE` default: empty, which means use the default profile from the YAML file
- `LLM_MAX_PROMPT_CHARS` default: `20000`
- `LLM_MAX_SNIPPET_CHARS` default: `1200`

Local model or secret configuration under `config/` and `llm.yaml` is ignored and not published.

When `LLM_ENABLED=true` and the file at `LLM_CONFIG_PATH` exists, the worker loads the routed provider/model from that YAML file and uses it to generate a richer beginner guide. In this workspace the intended config path is [`config/llm.yaml`](D:/ai-agent/new-local-learn/config/llm.yaml). If the file is missing, invalid, or the provider request fails, the pipeline falls back to the deterministic built-in tutor composer instead of failing the whole task.

## Run Locally

Start Redis:

```powershell
docker compose up -d redis
```

Start the API:

```powershell
uvicorn app.main:app --reload
```

Start the worker in a second terminal:

```powershell
arq app.tasks.worker.WorkerSettings
```

The API will be available at `http://127.0.0.1:8000`.

Request and task execution now emit structured JSON logs with request ids and task stage transitions.

The Vue workbench can optionally send `X-API-Key` automatically when `VITE_API_KEY` is configured in its environment.
The workbench also persists the returned `task_token` and reuses it for status polling, SSE streaming, result reads, and browser artifact downloads.
It can also attach `Authorization: Bearer <token>` when `VITE_ACCESS_TOKEN` is set or when an access token is saved in the shell UI.

If the frontend is deployed on a different origin, configure `CORS_ALLOWED_ORIGINS` with a comma-separated allowlist.
If you want to protect task creation and metrics in a private deployment, configure `API_KEYS` with a comma-separated allowlist and send `X-API-Key` on requests.
If you want scoped service credentials instead of all-access legacy keys, configure `API_KEY_RECORDS` with semicolon-separated records in the form `subject:key:scope1|scope2`.
If you want OIDC bearer-token protection, configure `OIDC_ISSUER_URL`, `OIDC_AUDIENCE`, and `OIDC_JWKS_URL`. Optional settings `OIDC_SCOPE_CLAIM`, `OIDC_SUBJECT_CLAIM`, `OIDC_ALGORITHMS`, and `OIDC_JWKS_CACHE_SECONDS` let you adapt to provider-specific claim names and signing algorithms.
`TASK_TTL_SECONDS` controls Redis retention for task status, results, and SSE events. `ARTIFACT_TTL_SECONDS` controls opportunistic cleanup of old task artifact directories whenever new analysis jobs start.
When `API_KEYS` or `API_KEY_RECORDS` is configured, task submission still uses `X-API-Key`, but each accepted task also returns its own `task_token`. Subsequent reads for that task can use either a suitably scoped API key or the task-specific token.
When OIDC is configured, protected endpoints also accept `Authorization: Bearer <access token>` and apply the same scope checks to token claims.
Supported service scopes are `analyze:create`, `tasks:read`, `tasks:write`, `artifacts:read`, `metrics:read`, and `audit:read`. Legacy `API_KEYS` still grant full access for backward compatibility.

## Docker Compose

Create an environment file:

```powershell
Copy-Item .env.example .env
```

Then start the full stack:

```powershell
docker compose up --build
```

This brings up:

- `redis` for queue and task state
- `api` on `http://127.0.0.1:8000`
- `worker` for background analysis jobs

The compose stack mounts `./artifacts` into both runtime containers so generated reports survive container restarts.
Set `LLM_ENABLED=true` and provide a real `config/llm.yaml` inside the container image or via your own bind mount/derived image if you want model-enhanced tutorial output in containerized runs.

## API Endpoints

Submit a repository for analysis:

```http
POST /api/v1/analyze
Content-Type: application/json

{
  "github_url": "https://github.com/owner/repo"
}
```

Example accepted response:

```json
{
  "task_id": "abc123",
  "status_url": "/api/v1/tasks/abc123",
  "result_url": "/api/v1/tasks/abc123/result",
  "stream_url": "/api/v1/tasks/abc123/stream",
  "task_token": "task-specific-secret"
}
```

Task lifecycle endpoints:

- `GET /api/v1/tasks` returns a paginated recent-task view for operations tooling
- `GET /api/v1/tasks/{task_id}` returns task status and progress
- `GET /api/v1/tasks/{task_id}/result` returns the analysis result or a `202` payload while still running
- `GET /api/v1/tasks/{task_id}/stream` returns task events as Server-Sent Events
- `POST /api/v1/tasks/{task_id}/cancel` marks a queued or running task for cancellation
- `POST /api/v1/tasks/{task_id}/retry` requeues a failed or cancelled task as a brand new task id
- `GET /api/v1/tasks/{task_id}/artifacts/markdown` downloads the generated Markdown report
- `GET /api/v1/tasks/{task_id}/artifacts/html` downloads the generated HTML report
- `GET /api/v1/tasks/{task_id}/artifacts/pdf` downloads the generated PDF report
- `GET /api/v1/audit/events` returns recent persisted audit events
- `GET /healthz` returns a basic service health payload for orchestration and smoke checks
- `GET /readyz` verifies Redis connectivity for readiness checks
- `GET /metrics` exposes Prometheus-style counters

If API protection is enabled, task read endpoints accept either:

- `X-API-Key: <global key>`
- `Authorization: Bearer <access token>`
- `X-Task-Token: <task token>`
- `?task_token=<task token>` for browser EventSource clients
- `?task_token=<task token>` or `?api_key=<global key>` for browser artifact downloads

When rate limiting is triggered, `POST /api/v1/analyze` returns `429` with `Retry-After`, `X-RateLimit-Limit`, and `X-RateLimit-Remaining`.
The metrics endpoint now also includes LLM counters such as request, success, and fallback totals when the optional tutorial enhancer is enabled.
Successful analysis results now also include `agent_metadata` describing the executed analysis DAG, node dependencies, execution modes, and any tutorial-generation fallback.
Audit events are written to Redis as a capped rolling window and can be queried through `/api/v1/audit/events` when an API key with `audit:read` is available.
`GET /api/v1/audit/events` supports `limit`, `offset`, `action`, `outcome`, `task_id`, `request_id`, `subject`, `method`, and `path` query filters and returns `{ events, total, limit, offset }`.
`GET /api/v1/tasks` supports `limit`, `offset`, and optional `state`, returning recent task metadata including the original `github_url`.

## Operations UI

The Vue admin console now includes:

- a recent task panel with state filtering and direct links to task detail pages
- a metrics snapshot panel for backend counters
- an audit event panel with filtering and pagination
- cancel and retry controls on the task detail page for supported task states

## Container Build

Build the backend image:

```powershell
docker build -t github-tech-doc-generator .
```

Run the API container against a reachable Redis instance:

```powershell
docker run --rm -p 8000:8000 `
  -e REDIS_URL=redis://host.docker.internal:6379/0 `
  -e LOG_LEVEL=INFO `
  github-tech-doc-generator
```

Run a worker container from the same image:

```powershell
docker run --rm `
  -e REDIS_URL=redis://host.docker.internal:6379/0 `
  -e WORKER_MAX_JOBS=10 `
  github-tech-doc-generator `
  arq app.tasks.worker.WorkerSettings
```

The repository also includes a ready-to-run [`docker-compose.yml`](D:/ai-agent/new-local-learn/docker-compose.yml) and a sample [`.env.example`](D:/ai-agent/new-local-learn/.env.example) for local multi-container deployment.

## Test

```powershell
python -m pytest
```

## CI

The root repository now includes a GitHub Actions workflow at [`.github/workflows/backend-ci.yml`](D:/ai-agent/new-local-learn/.github/workflows/backend-ci.yml). It runs the backend test suite on pushes and pull requests, then validates that the production Docker image still builds successfully.

The separate Vue frontend workbench repository also has its own workflow at [`.github/workflows/frontend-ci.yml`](C:/Users/20856/.config/superpowers/worktrees/new-local-learn/vue-frontend-workbench/.github/workflows/frontend-ci.yml) to run `npm test -- --run` and `npm run build`.

## Notes

- Generated reports are written under `artifacts/` as `result.md`, `result.html`, and `result.pdf`.
- Redis is required for the normal task store flow.
- The API and worker now share the same Redis-backed queue/state backend.
- The root repository is safe to publish because local secrets and model config files are ignored.
