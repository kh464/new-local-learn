from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from app.core.models import (
    AnalysisResult,
    BackendRouteSummary,
    BackendSummary,
    DetectedStackSummary,
    FrontendApiCallSummary,
    FrontendRouteSummary,
    FrontendSummary,
    LogicFlowSummary,
    LogicSummary,
    MermaidSections,
    RepositorySummary,
    TutorialSummary,
)
from app.main import create_app
from app.storage.task_store import RedisTaskStore


@pytest.fixture
def tmp_path() -> Path:
    base = Path.cwd() / "tmpbase"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir()
    return path


@pytest_asyncio.fixture
async def fakeredis_client():
    client = FakeRedis()
    try:
        yield client
    finally:
        result = client.aclose()
        if inspect.isawaitable(result):
            await result


@pytest_asyncio.fixture
async def fake_job_context(fakeredis_client, tmp_path: Path):
    store = RedisTaskStore(fakeredis_client)
    repo_root = tmp_path / "source-repo"
    repo_root.mkdir()
    (repo_root / "app").mkdir()
    (repo_root / "web").mkdir()
    (repo_root / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\nasync def health():\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (repo_root / "web" / "App.tsx").write_text(
        "import 'react-router-dom'\n\nfetch('/health')\n",
        encoding="utf-8",
    )
    (repo_root / "pyproject.toml").write_text('[project]\ndependencies = ["fastapi"]\n', encoding="utf-8")
    (repo_root / "package.json").write_text('{"dependencies":{"react":"18.2.0"}}\n', encoding="utf-8")

    settings = SimpleNamespace(
        artifacts_dir=tmp_path / "artifacts",
        max_file_count=2000,
        max_file_bytes=50000,
    )

    async def clone_repo(github_url: str, destination):
        return repo_root

    async def read_files(repo_path: Path, file_list: list[str]) -> dict[str, str]:
        contents: dict[str, str] = {}
        for relative_path in file_list:
            path = repo_path / relative_path
            if path.is_file():
                contents[relative_path] = path.read_text(encoding="utf-8")
        return contents

    return {
        "redis": fakeredis_client,
        "task_store": store,
        "settings": settings,
        "clone_repo": clone_repo,
        "read_files": read_files,
    }


@pytest_asyncio.fixture
async def api_client(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    app = create_app(task_store=store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_analysis_result(tmp_path: Path) -> AnalysisResult:
    markdown_path = tmp_path / "artifacts" / "task-1" / "result.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text("# Result\n", encoding="utf-8")
    repo_path = tmp_path / "source-repo"
    repo_path.mkdir(exist_ok=True)
    return AnalysisResult(
        github_url="https://github.com/octocat/Hello-World",
        repo_path=str(repo_path),
        markdown_path=str(markdown_path),
        repo_summary=RepositorySummary(
            name="Hello-World",
            files=["app/main.py", "web/App.tsx"],
            key_files=["pyproject.toml", "package.json"],
            file_count=4,
        ),
        detected_stack=DetectedStackSummary(
            frameworks=["fastapi", "react"],
            languages=["python", "typescript"],
        ),
        backend_summary=BackendSummary(
            routes=[BackendRouteSummary(method="GET", path="/health", source_file="app/main.py")]
        ),
        frontend_summary=FrontendSummary(
            routing=[FrontendRouteSummary(path="/", source_file="web/App.tsx")],
            api_calls=[FrontendApiCallSummary(url="/health", source_file="web/App.tsx")],
        ),
        logic_summary=LogicSummary(
            flows=[
                LogicFlowSummary(
                    frontend_call="/health",
                    frontend_source="web/App.tsx",
                    backend_route="/health",
                    backend_source="app/main.py",
                    backend_method="GET",
                    confidence=0.9,
                )
            ]
        ),
        tutorial_summary=TutorialSummary(
            mental_model="Frontend hits a FastAPI backend.",
            run_steps=["Install dependencies", "Start the API", "Open the app"],
            pitfalls=["Missing environment variables"],
            self_check_questions=["Which route serves health?"],
        ),
        mermaid_sections=MermaidSections(system="graph TD\n  A[Client] --> B[API]"),
    )
