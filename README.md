# new-local-learn

`new-local-learn` is the repository root for a GitHub technical document generator. The current tracked codebase is a Python backend MVP that accepts a GitHub repository URL, runs an asynchronous analysis pipeline, and produces a Markdown report with stack detection, route summaries, logic mapping, and Mermaid diagrams.

## What This Repository Contains

- FastAPI API for task submission and result retrieval
- Redis-backed task state storage
- ARQ worker pipeline for repository analysis
- Repository scanning, stack detection, backend/frontend analysis, and tutorial composition
- Markdown and Mermaid report generation
- Automated tests for API, pipeline, storage, and analyzers

## Current Scope

This root repository currently tracks the backend service.

There is also a local `vue-frontend-workbench/` directory in the workspace, but it is a separate Git worktree/repository and is intentionally not included in this root repository push.

## Architecture Overview

1. Client submits a GitHub repository URL to `POST /api/v1/analyze`.
2. The backend creates a task id and exposes status, result, and stream endpoints.
3. The worker clones and scans the target repository.
4. Analyzer services detect frameworks/languages, summarize backend and frontend behavior, and map cross-layer flows.
5. The document compiler emits a Markdown report and Mermaid diagram under `artifacts/`.

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
docker-compose.yml     local Redis service
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

Available settings in code today:

- `REDIS_URL` default: `redis://localhost:6379/0`
- `ARTIFACTS_DIR` default: `artifacts`
- `WORKSPACE_DIR` default: `artifacts/workspace`
- `MAX_FILE_COUNT` default: `2000`
- `MAX_FILE_BYTES` default: `50000`

Local model or secret configuration under `config/` and `llm.yaml` is ignored and not published.

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

## API Endpoints

Submit a repository for analysis:

```http
POST /api/v1/analyze
Content-Type: application/json

{
  "github_url": "https://github.com/owner/repo"
}
```

Task lifecycle endpoints:

- `GET /api/v1/tasks/{task_id}` returns task status and progress
- `GET /api/v1/tasks/{task_id}/result` returns the analysis result or a `202` payload while still running
- `GET /api/v1/tasks/{task_id}/stream` returns task events as Server-Sent Events

## Test

```powershell
python -m pytest
```

## Notes

- Generated reports are written under `artifacts/`.
- Redis is required for the normal task store flow.
- The root repository is safe to publish because local secrets and model config files are ignored.
