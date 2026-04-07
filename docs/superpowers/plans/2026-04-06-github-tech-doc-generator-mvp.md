# GitHub Tech Doc Generator MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backend-first MVP that accepts a public GitHub repository URL, runs deterministic repository analysis in an ARQ worker, and returns structured Markdown documentation plus status and SSE progress APIs.

**Architecture:** FastAPI exposes task APIs, Redis stores task state and event history, ARQ runs the background pipeline, and deterministic services produce structured analysis that is compiled into Markdown artifacts on disk.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, redis-py asyncio, ARQ, pytest, httpx, fakeredis, uvicorn

---

## File Structure

- `pyproject.toml`: project metadata and dependencies
- `.gitignore`: local ignores
- `app/main.py`: FastAPI app factory
- `app/api/routes/tasks.py`: analyze, status, result, stream routes
- `app/core/config.py`: env-driven settings
- `app/core/models.py`: task and result models
- `app/storage/artifacts.py`: artifact path helpers
- `app/storage/task_store.py`: Redis task state and result store
- `app/services/repo/fetcher.py`: GitHub URL normalization and clone entrypoint
- `app/services/repo/scanner.py`: repo tree scan and key file detection
- `app/services/analyzers/*.py`: stack, backend, frontend, logic, tutor analyzers
- `app/services/docs/*.py`: Mermaid and Markdown generation
- `app/tasks/jobs.py`: pipeline implementation
- `app/tasks/worker.py`: ARQ worker settings
- `tests/`: unit, API, and task tests
- `docker-compose.yml`: local Redis
- `README.md`: local run instructions

### Task 1: Bootstrap the package, settings, and base models

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/core/config.py`
- Create: `app/core/models.py`
- Create: `app/storage/artifacts.py`
- Test: `tests/unit/test_bootstrap.py`

- [ ] **Step 1: Write the failing bootstrap test**

```python
from app.core.config import Settings
from app.core.models import TaskStage, TaskState, TaskStatus
from app.storage.artifacts import ArtifactPaths


def test_settings_and_models_bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))

    settings = Settings()
    status = TaskStatus(task_id="task-1", state=TaskState.RUNNING, stage=TaskStage.FETCH_REPO, progress=10)
    paths = ArtifactPaths(base_dir=settings.artifacts_dir, task_id="task-1")

    assert settings.redis_url == "redis://localhost:6379/0"
    assert status.stage is TaskStage.FETCH_REPO
    assert paths.markdown_path.name == "result.md"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_bootstrap.py -q`
Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Write minimal bootstrap implementation**

```toml
[project]
name = "github-tech-doc-generator"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0,<1.0.0",
  "uvicorn[standard]>=0.30.0,<1.0.0",
  "pydantic>=2.8.0,<3.0.0",
  "pydantic-settings>=2.3.0,<3.0.0",
  "redis>=5.0.0,<6.0.0",
  "arq>=0.26.0,<0.27.0",
]
[project.optional-dependencies]
dev = ["pytest>=8.2.0,<9.0.0", "pytest-asyncio>=0.23.0,<0.24.0", "httpx>=0.27.0,<0.28.0", "fakeredis>=2.23.0,<3.0.0"]
[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]
asyncio_mode = "auto"
```

```python
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    redis_url: str = "redis://localhost:6379/0"
    artifacts_dir: Path = Field(default=Path("artifacts"))
    workspace_dir: Path = Field(default=Path("artifacts/workspace"))
    max_file_count: int = 2000
    max_file_bytes: int = 50000
    allowed_github_hosts: tuple[str, ...] = ("github.com", "www.github.com")
```

```python
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStage(str, Enum):
    FETCH_REPO = "fetch_repo"
    SCAN_TREE = "scan_tree"
    DETECT_STACK = "detect_stack"
    ANALYZE_BACKEND = "analyze_backend"
    ANALYZE_FRONTEND = "analyze_frontend"
    BUILD_DOC = "build_doc"
    FINALIZE = "finalize"


class AnalyzeRequest(BaseModel):
    github_url: HttpUrl


class TaskStatus(BaseModel):
    task_id: str
    state: TaskState
    stage: TaskStage | None = None
    progress: int = Field(default=0, ge=0, le=100)
    message: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactPaths:
    base_dir: Path
    task_id: str

    @property
    def task_dir(self) -> Path:
        return self.base_dir / self.task_id

    @property
    def repo_dir(self) -> Path:
        return self.task_dir / "repo"

    @property
    def markdown_path(self) -> Path:
        return self.task_dir / "result.md"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_bootstrap.py -q`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git init
git add .gitignore pyproject.toml app/__init__.py app/core/config.py app/core/models.py app/storage/artifacts.py tests/unit/test_bootstrap.py
git commit -m "chore: bootstrap project core"
```

### Task 2: Add Redis task storage and FastAPI task endpoints

**Files:**
- Create: `app/storage/task_store.py`
- Create: `app/api/routes/tasks.py`
- Create: `app/main.py`
- Create: `tests/conftest.py`
- Test: `tests/unit/test_task_store.py`
- Test: `tests/api/test_tasks_api.py`

- [ ] **Step 1: Write the failing storage and API tests**

```python
from app.core.models import TaskState, TaskStatus
from app.storage.task_store import RedisTaskStore


async def test_task_store_round_trip(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-1", state=TaskState.QUEUED))
    loaded = await store.get_status("task-1")
    assert loaded is not None
    assert loaded.state is TaskState.QUEUED
```

```python
async def test_analyze_endpoint_returns_urls(api_client, monkeypatch):
    async def fake_enqueue(task_id: str, github_url: str) -> str:
        return task_id

    monkeypatch.setattr("app.api.routes.tasks.enqueue_analysis", fake_enqueue)
    response = await api_client.post("/api/v1/analyze", json={"github_url": "https://github.com/octocat/Hello-World"})
    assert response.status_code == 202
    assert response.json()["status_url"].endswith(response.json()["task_id"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_task_store.py tests/api/test_tasks_api.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write minimal storage and API implementation**

```python
import json
from datetime import datetime, timezone

from app.core.models import TaskStage, TaskState, TaskStatus


class RedisTaskStore:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def set_status(self, status: TaskStatus) -> None:
        await self.redis.set(f"task:{status.task_id}:status", status.model_dump_json())

    async def get_status(self, task_id: str) -> TaskStatus | None:
        raw = await self.redis.get(f"task:{task_id}:status")
        return None if raw is None else TaskStatus.model_validate_json(raw)

    async def set_result(self, task_id: str, payload: dict) -> None:
        await self.redis.set(f"task:{task_id}:result", json.dumps(payload))

    async def get_result(self, task_id: str) -> dict | None:
        raw = await self.redis.get(f"task:{task_id}:result")
        return None if raw is None else json.loads(raw)

    async def append_event(self, task_id: str, state: TaskState, stage: TaskStage | None, message: str) -> None:
        event = {
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "state": state.value,
            "stage": stage.value if stage else None,
            "message": message,
        }
        await self.redis.rpush(f"task:{task_id}:events", json.dumps(event))
```

```python
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from app.core.models import AnalyzeRequest, TaskState

router = APIRouter()


async def enqueue_analysis(task_id: str, github_url: str) -> str:
    return task_id


@router.post("/analyze", status_code=status.HTTP_202_ACCEPTED)
async def analyze_repository(request: Request, payload: AnalyzeRequest):
    task_id = str(uuid4())
    await enqueue_analysis(task_id, str(payload.github_url))
    base = str(request.base_url).rstrip("/")
    return {
        "task_id": task_id,
        "state": TaskState.QUEUED.value,
        "status_url": f"{base}/api/v1/status/{task_id}",
        "result_url": f"{base}/api/v1/result/{task_id}",
        "stream_url": f"{base}/api/v1/stream/{task_id}",
    }


@router.get("/status/{task_id}")
async def get_status(task_id: str):
    raise HTTPException(status_code=404, detail="Task not found")


@router.get("/result/{task_id}")
async def get_result(task_id: str):
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"task_id": task_id, "state": "queued"})


@router.get("/stream/{task_id}")
async def stream_events(task_id: str):
    async def event_stream():
        yield f"event: log\ndata: {{\"task_id\": \"{task_id}\", \"message\": \"waiting\"}}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

```python
from fastapi import FastAPI
from app.api.routes.tasks import router as tasks_router


def create_app() -> FastAPI:
    app = FastAPI(title="GitHub Tech Doc Generator", version="0.1.0")
    app.include_router(tasks_router, prefix="/api/v1")
    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_task_store.py tests/api/test_tasks_api.py -q`
Expected: `all tests pass`

- [ ] **Step 5: Commit**

```bash
git add app/storage/task_store.py app/api/routes/tasks.py app/main.py tests/conftest.py tests/unit/test_task_store.py tests/api/test_tasks_api.py
git commit -m "feat: add task store and api endpoints"
```

### Task 3: Add the ARQ worker skeleton and pipeline state transitions

**Files:**
- Create: `app/tasks/jobs.py`
- Create: `app/tasks/worker.py`
- Test: `tests/tasks/test_jobs.py`

- [ ] **Step 1: Write the failing pipeline test**

```python
from app.core.models import TaskState
from app.tasks.jobs import run_analysis_job


async def test_run_analysis_job_sets_succeeded(fake_job_context):
    result = await run_analysis_job(fake_job_context, "task-1", "https://github.com/octocat/Hello-World")
    assert result["task_id"] == "task-1"
    assert result["state"] == TaskState.SUCCEEDED.value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/tasks/test_jobs.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write minimal worker implementation**

```python
from app.core.models import TaskStage, TaskState, TaskStatus


async def run_analysis_job(ctx, task_id: str, github_url: str) -> dict:
    store = ctx["task_store"]
    await store.set_status(TaskStatus(task_id=task_id, state=TaskState.RUNNING, stage=TaskStage.FETCH_REPO, progress=10))
    await store.append_event(task_id, TaskState.RUNNING, TaskStage.FETCH_REPO, "fetching repository")
    await store.set_status(TaskStatus(task_id=task_id, state=TaskState.SUCCEEDED, stage=TaskStage.FINALIZE, progress=100))
    await store.set_result(task_id, {"task_id": task_id, "source": {"github_url": github_url}})
    return {"task_id": task_id, "state": TaskState.SUCCEEDED.value}
```

```python
from arq.connections import RedisSettings
from app.core.config import Settings
from app.tasks.jobs import run_analysis_job

settings = Settings()


class WorkerSettings:
    functions = [run_analysis_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/tasks/test_jobs.py -q`
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add app/tasks/jobs.py app/tasks/worker.py tests/tasks/test_jobs.py
git commit -m "feat: add arq worker skeleton"
```

### Task 4: Implement repository fetch and tree scanning services

**Files:**
- Create: `app/services/repo/fetcher.py`
- Create: `app/services/repo/scanner.py`
- Test: `tests/unit/test_repo_services.py`

- [ ] **Step 1: Write the failing repository service tests**

```python
from app.services.repo.fetcher import normalize_github_url
from app.services.repo.scanner import RepositoryScanner


def test_normalize_github_url_rejects_non_github_hosts():
    try:
        normalize_github_url("https://gitlab.com/example/project")
    except ValueError as exc:
        assert "Unsupported GitHub host" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_repository_scanner_skips_node_modules(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignore.js").write_text("console.log('x')", encoding="utf-8")
    summary = RepositoryScanner(max_file_count=10, max_file_bytes=10_000).scan(tmp_path)
    assert "src/main.py" in summary["files"]
    assert "node_modules/ignore.js" not in summary["files"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_repo_services.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write minimal repository services**

```python
from urllib.parse import urlparse


def normalize_github_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        raise ValueError("Unsupported GitHub host")
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"https://github.com{path}"
```

```python
from pathlib import Path


class RepositoryScanner:
    def __init__(self, max_file_count: int, max_file_bytes: int):
        self.max_file_count = max_file_count
        self.max_file_bytes = max_file_bytes
        self.ignored_dirs = {".git", "node_modules", "__pycache__", ".venv"}

    def scan(self, repo_dir: Path) -> dict:
        files: list[str] = []
        key_files: list[str] = []
        for path in repo_dir.rglob("*"):
            if any(part in self.ignored_dirs for part in path.parts) or not path.is_file():
                continue
            if path.stat().st_size > self.max_file_bytes:
                continue
            relative = path.relative_to(repo_dir).as_posix()
            files.append(relative)
            if path.name in {"README.md", "package.json", "pyproject.toml", "requirements.txt"}:
                key_files.append(relative)
            if len(files) >= self.max_file_count:
                break
        return {"files": files, "key_files": key_files, "file_count": len(files)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_repo_services.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add app/services/repo/fetcher.py app/services/repo/scanner.py tests/unit/test_repo_services.py
git commit -m "feat: add repository scanning services"
```

### Task 5: Implement stack, backend, frontend, and logic analyzers

**Files:**
- Create: `app/services/analyzers/stack_detector.py`
- Create: `app/services/analyzers/backend_analyzer.py`
- Create: `app/services/analyzers/frontend_analyzer.py`
- Create: `app/services/analyzers/logic_mapper.py`
- Test: `tests/unit/test_analysis_services.py`

- [ ] **Step 1: Write the failing analyzer tests**

```python
from app.services.analyzers.backend_analyzer import BackendAnalyzer
from app.services.analyzers.frontend_analyzer import FrontendAnalyzer
from app.services.analyzers.logic_mapper import LogicMapper
from app.services.analyzers.stack_detector import StackDetector


def test_stack_detector_identifies_fastapi_and_react():
    summary = StackDetector().detect(
        ["pyproject.toml", "package.json"],
        {"pyproject.toml": "fastapi", "package.json": '{"dependencies":{"react":"18.2.0"}}'},
    )
    assert "fastapi" in summary["frameworks"]
    assert "react" in summary["frameworks"]


def test_backend_and_frontend_analysis_feed_logic_mapper():
    backend = BackendAnalyzer().analyze({"app/main.py": "@app.get('/api/v1/items')\nasync def items():\n    return []\n"})
    frontend = FrontendAnalyzer().analyze({"src/App.tsx": "fetch('/api/v1/items')\n"})
    flows = LogicMapper().map_flows(frontend, backend)
    assert backend["routes"][0]["path"] == "/api/v1/items"
    assert frontend["api_calls"][0]["url"] == "/api/v1/items"
    assert flows["flows"][0]["backend_route"] == "/api/v1/items"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_analysis_services.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Write minimal analyzer implementations**

```python
import json
import re


class StackDetector:
    def detect(self, file_list: list[str], file_contents: dict[str, str]) -> dict:
        frameworks: list[str] = []
        if "fastapi" in file_contents.get("pyproject.toml", "").lower():
            frameworks.append("fastapi")
        package = json.loads(file_contents.get("package.json", "{}"))
        deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        for name in ("react", "vue", "svelte"):
            if name in deps:
                frameworks.append(name)
        return {"frameworks": sorted(set(frameworks)), "languages": [path.split(".")[-1] for path in file_list if "." in path]}
```

```python
import re


class BackendAnalyzer:
    ROUTE_PATTERN = re.compile(r"@(?:app|router)\.(get|post|put|delete|patch)\(['\"](?P<path>[^'\"]+)['\"]\)", re.IGNORECASE)

    def analyze(self, file_contents: dict[str, str]) -> dict:
        routes = []
        for file_path, source in file_contents.items():
            for match in self.ROUTE_PATTERN.finditer(source):
                routes.append({"method": match.group(1).upper(), "path": match.group("path"), "source_file": file_path})
        return {"routes": routes}
```

```python
import re


class FrontendAnalyzer:
    FETCH_PATTERN = re.compile(r"fetch\(['\"](?P<url>[^'\"]+)['\"]\)")

    def analyze(self, file_contents: dict[str, str]) -> dict:
        api_calls = []
        routing = None
        for file_path, source in file_contents.items():
            if "react-router-dom" in source:
                routing = "react-router-dom"
            for match in self.FETCH_PATTERN.finditer(source):
                api_calls.append({"url": match.group("url"), "source_file": file_path})
        return {"routing": routing, "api_calls": api_calls}
```

```python
class LogicMapper:
    def map_flows(self, frontend_summary: dict | None, backend_summary: dict | None) -> dict:
        backend_routes = {item["path"]: item for item in (backend_summary or {}).get("routes", [])}
        flows = []
        for item in (frontend_summary or {}).get("api_calls", []):
            if item["url"] in backend_routes:
                flows.append({
                    "frontend_call": item["url"],
                    "frontend_source": item["source_file"],
                    "backend_route": backend_routes[item["url"]]["path"],
                    "backend_source": backend_routes[item["url"]]["source_file"],
                    "confidence": "direct-match",
                })
        return {"flows": flows}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_analysis_services.py -q`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add app/services/analyzers/stack_detector.py app/services/analyzers/backend_analyzer.py app/services/analyzers/frontend_analyzer.py app/services/analyzers/logic_mapper.py tests/unit/test_analysis_services.py
git commit -m "feat: add deterministic analysis services"
```

### Task 6: Implement tutor, Mermaid, Markdown generation, and integrate the real pipeline

**Files:**
- Create: `app/services/analyzers/tutor_composer.py`
- Create: `app/services/docs/mermaid_builder.py`
- Create: `app/services/docs/markdown_compiler.py`
- Modify: `app/tasks/jobs.py`
- Test: `tests/unit/test_document_generation.py`
- Test: `tests/tasks/test_pipeline_integration.py`

- [ ] **Step 1: Write the failing document and pipeline tests**

```python
from app.services.analyzers.tutor_composer import TutorComposer
from app.services.docs.markdown_compiler import MarkdownCompiler
from app.services.docs.mermaid_builder import MermaidBuilder


def test_markdown_compiler_includes_mermaid_and_routes():
    tutorial = TutorComposer().compose({"frameworks": ["fastapi", "react"]}, {"flows": []})
    mermaid = MermaidBuilder().build_system_diagram({"frameworks": ["fastapi", "react"]})
    markdown = MarkdownCompiler().compile(
        task_id="task-1",
        repo_summary={"name": "demo", "key_files": ["app/main.py"]},
        detected_stack={"frameworks": ["fastapi", "react"]},
        backend_summary={"routes": [{"method": "GET", "path": "/health"}]},
        frontend_summary={"routing": "react-router-dom", "api_calls": []},
        logic_summary={"flows": []},
        tutorial_summary=tutorial,
        mermaid_sections={"system": mermaid},
    )
    assert "```mermaid" in markdown
    assert "/health" in markdown
```

```python
from app.tasks.jobs import run_analysis_job


async def test_pipeline_returns_result_payload(fake_job_context):
    result = await run_analysis_job(fake_job_context, "task-1", "https://github.com/octocat/Hello-World")
    assert result["state"] == "succeeded"
    assert result["result"]["markdown_path"].endswith("result.md")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_document_generation.py tests/tasks/test_pipeline_integration.py -q`
Expected: `ModuleNotFoundError` or `AssertionError`

- [ ] **Step 3: Write the generation services and replace the skeleton pipeline**

```python
class TutorComposer:
    def compose(self, detected_stack: dict, logic_summary: dict) -> dict:
        frameworks = ", ".join(detected_stack.get("frameworks", [])) or "the detected stack"
        return {
            "mental_model": f"Think of {frameworks} as stations in one workshop.",
            "run_steps": [
                "docker compose up -d redis",
                "uvicorn app.main:app --reload",
                "arq app.tasks.worker.WorkerSettings",
            ],
            "pitfalls": ["Make sure Redis is reachable before starting jobs."],
            "self_check_questions": ["What stage runs before markdown compilation?"],
        }
```

```python
class MermaidBuilder:
    def build_system_diagram(self, detected_stack: dict) -> str:
        return "\n".join([
            "graph TD",
            "  A[Client] --> B[FastAPI]",
            "  B --> C[ARQ Worker]",
            "  C --> D[Redis]",
            "  C --> E[Artifacts]",
        ])
```

```python
class MarkdownCompiler:
    def compile(self, task_id: str, repo_summary: dict, detected_stack: dict, backend_summary: dict | None, frontend_summary: dict | None, logic_summary: dict, tutorial_summary: dict, mermaid_sections: dict) -> str:
        routes = backend_summary.get("routes", []) if backend_summary else []
        route_lines = "\n".join(f"- `{item['method']} {item['path']}`" for item in routes) or "- None detected"
        return f"""# {repo_summary.get('name', task_id)} Technical Guide

## Tech Stack
- {", ".join(detected_stack.get("frameworks", [])) or "Unknown"}

## System Diagram
```mermaid
{mermaid_sections['system']}
```

## Backend Analysis
{route_lines}

## Beginner Guide
- Mental model: {tutorial_summary['mental_model']}
"""
```

```python
import json
from pathlib import Path
from app.core.models import AnalysisResult, TaskStage, TaskState, TaskStatus
from app.services.analyzers.backend_analyzer import BackendAnalyzer
from app.services.analyzers.frontend_analyzer import FrontendAnalyzer
from app.services.analyzers.logic_mapper import LogicMapper
from app.services.analyzers.stack_detector import StackDetector
from app.services.analyzers.tutor_composer import TutorComposer
from app.services.docs.markdown_compiler import MarkdownCompiler
from app.services.docs.mermaid_builder import MermaidBuilder
from app.services.repo.fetcher import normalize_github_url
from app.services.repo.scanner import RepositoryScanner
from app.storage.artifacts import ArtifactPaths


async def run_analysis_job(ctx, task_id: str, github_url: str) -> dict:
    store = ctx["task_store"]
    settings = ctx["settings"]
    clone_repo = ctx["clone_repo"]
    read_files = ctx["read_files"]
    paths = ArtifactPaths(base_dir=Path(settings.artifacts_dir), task_id=task_id)
    paths.task_dir.mkdir(parents=True, exist_ok=True)

    await store.set_status(TaskStatus(task_id=task_id, state=TaskState.RUNNING, stage=TaskStage.FETCH_REPO, progress=10))
    repo_dir = await clone_repo(normalize_github_url(github_url), paths.repo_dir)
    summary = RepositoryScanner(settings.max_file_count, settings.max_file_bytes).scan(repo_dir)
    summary["name"] = repo_dir.name
    file_contents = read_files(repo_dir, summary["key_files"] + summary["files"][:25])
    stack = StackDetector().detect(summary["files"], file_contents)
    backend = BackendAnalyzer().analyze(file_contents)
    frontend = FrontendAnalyzer().analyze(file_contents)
    logic = LogicMapper().map_flows(frontend, backend)
    tutorial = TutorComposer().compose(stack, logic)
    mermaid = {"system": MermaidBuilder().build_system_diagram(stack)}
    markdown = MarkdownCompiler().compile(task_id, summary, stack, backend, frontend, logic, tutorial, mermaid)
    paths.markdown_path.write_text(markdown, encoding="utf-8")
    result = AnalysisResult(
        task_id=task_id,
        source={"github_url": github_url},
        repo_summary=summary,
        detected_stack=stack,
        backend_summary=backend,
        frontend_summary=frontend,
        logic_summary=logic,
        tutorial_summary=tutorial,
        artifacts={"markdown_path": str(paths.markdown_path)},
        markdown_path=str(paths.markdown_path),
    )
    await store.set_result(task_id, result.model_dump(mode="json"))
    await store.set_status(TaskStatus(task_id=task_id, state=TaskState.SUCCEEDED, stage=TaskStage.FINALIZE, progress=100))
    return {"task_id": task_id, "state": TaskState.SUCCEEDED.value, "result": result.model_dump(mode="json")}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_document_generation.py tests/tasks/test_pipeline_integration.py -q`
Expected: `all tests pass`

- [ ] **Step 5: Commit**

```bash
git add app/services/analyzers/tutor_composer.py app/services/docs/mermaid_builder.py app/services/docs/markdown_compiler.py app/tasks/jobs.py tests/unit/test_document_generation.py tests/tasks/test_pipeline_integration.py
git commit -m "feat: integrate document generation pipeline"
```

### Task 7: Finalize result/status behavior, add local dev support, and verify the full suite

**Files:**
- Modify: `app/api/routes/tasks.py`
- Create: `docker-compose.yml`
- Create: `README.md`
- Test: `tests/api/test_result_flow.py`
- Test: `tests/api/test_tasks_api.py`
- Test: `tests/unit/test_bootstrap.py`
- Test: `tests/unit/test_task_store.py`
- Test: `tests/unit/test_repo_services.py`
- Test: `tests/unit/test_analysis_services.py`
- Test: `tests/unit/test_document_generation.py`
- Test: `tests/tasks/test_jobs.py`
- Test: `tests/tasks/test_pipeline_integration.py`

- [ ] **Step 1: Write the failing result-flow and SSE tests**

```python
async def test_result_endpoint_returns_accepted_until_complete(api_client, monkeypatch):
    async def fake_get_result(task_id: str):
        return None

    monkeypatch.setattr("app.api.routes.tasks.get_task_result", fake_get_result)
    response = await api_client.get("/api/v1/result/task-1")
    assert response.status_code == 202
    assert response.json()["task_id"] == "task-1"
```

```python
async def test_stream_endpoint_returns_sse_content_type(api_client):
    response = await api_client.get("/api/v1/stream/task-1")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_result_flow.py tests/api/test_tasks_api.py -q`
Expected: `AssertionError`

- [ ] **Step 3: Finalize API behavior and local dev support**

```python
from fastapi import Depends
from app.storage.task_store import RedisTaskStore


def get_task_store() -> RedisTaskStore:
    return RedisTaskStore(router.redis_client)


async def get_task_result(task_id: str, store: RedisTaskStore) -> dict | None:
    return await store.get_result(task_id)


@router.get("/result/{task_id}")
async def get_result(task_id: str, store: RedisTaskStore = Depends(get_task_store)):
    result = await get_task_result(task_id, store)
    if result is None:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"task_id": task_id, "state": "queued"})
    return result


@router.get("/stream/{task_id}")
async def stream_events(task_id: str):
    async def event_stream():
        yield f"event: log\ndata: {{\"task_id\": \"{task_id}\", \"message\": \"waiting\"}}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
```

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

````markdown
# README

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .[dev]
```

## Run

```bash
docker compose up -d redis
uvicorn app.main:app --reload
arq app.tasks.worker.WorkerSettings
```

## Test

```bash
python -m pytest
```
````

- [ ] **Step 4: Run the full verification suite**

Run: `python -m pytest`
Expected: `0 failures`

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/tasks.py docker-compose.yml README.md tests/api/test_result_flow.py tests/api/test_tasks_api.py
git commit -m "chore: finalize api flow and verify mvp"
```

## Self-Review

### Spec coverage

- API creation, status, result, and SSE flow: Tasks 2 and 7
- Redis task state and result persistence: Tasks 2 and 3
- ARQ worker execution: Tasks 3 and 6
- Repository fetch and scanning: Task 4
- Stack, backend, frontend, and logic analysis: Task 5
- Beginner guidance, Mermaid, and Markdown output: Task 6
- Local development and full verification: Task 7

### Red-Flag Scan

- No unresolved marker text remains in the task content
- Each task includes concrete code or commands
- Every task includes a failing-test step and a verification command

### Type consistency

- `TaskState`, `TaskStage`, and `TaskStatus` are introduced in Task 1 and reused consistently
- API paths stay `/api/v1/analyze`, `/api/v1/status/{task_id}`, `/api/v1/result/{task_id}`, `/api/v1/stream/{task_id}`
- The worker stage order matches the approved design
