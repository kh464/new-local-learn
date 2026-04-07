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
    CritiqueSummary,
    DetectedStackSummary,
    DeploySummary,
    DeployServiceSummary,
    EnvironmentVariableSummary,
    FrontendComponentSummary,
    FrontendApiCallSummary,
    FrontendRouteSummary,
    FrontendSummary,
    FrontendStateUnitSummary,
    KubernetesResourceSummary,
    LogicFlowSummary,
    LogicSummary,
    MermaidSections,
    RepositorySummary,
    TutorialCodeWalkthrough,
    TutorialFaqEntry,
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
    (repo_root / "k8s").mkdir()
    (repo_root / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\nasync def health():\n    return {'ok': True}\n",
        encoding="utf-8",
    )
    (repo_root / "web" / "App.tsx").write_text(
        "import 'react-router-dom'\n\nfetch('/health')\n",
        encoding="utf-8",
    )
    (repo_root / "pyproject.toml").write_text('[project]\ndependencies = ["fastapi"]\n', encoding="utf-8")
    (repo_root / "package.json").write_text(
        '{"dependencies":{"react":"18.2.0","vite":"5.0.0","zustand":"4.5.0"}}\n',
        encoding="utf-8",
    )
    (repo_root / "docker-compose.yml").write_text(
        "services:\n"
        "  redis:\n"
        "    image: redis:7-alpine\n"
        "    ports:\n"
        "      - \"6379:6379\"\n"
        "  api:\n"
        "    build: .\n"
        "    ports:\n"
        "      - \"8000:8000\"\n"
        "    depends_on:\n"
        "      - redis\n",
        encoding="utf-8",
    )
    (repo_root / ".env.example").write_text("REDIS_URL=redis://redis:6379/0\nAPI_KEYS=\n", encoding="utf-8")
    (repo_root / "k8s" / "api.yaml").write_text(
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n",
        encoding="utf-8",
    )

    settings = SimpleNamespace(
        artifacts_dir=tmp_path / "artifacts",
        max_file_count=2000,
        max_file_bytes=50000,
        max_total_bytes=2_000_000,
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
    async def enqueue_job(*args, **kwargs):
        return None

    store = RedisTaskStore(fakeredis_client)
    app = create_app(task_store=store)
    app.state.arq_redis = type("FakeQueue", (), {"enqueue_job": staticmethod(enqueue_job)})()
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
        html_path=str(markdown_path.with_suffix(".html")),
        pdf_path=str(markdown_path.with_suffix(".pdf")),
        repo_summary=RepositorySummary(
            name="Hello-World",
            files=["app/main.py", "web/App.tsx", "docker-compose.yml", ".env.example", "k8s/api.yaml"],
            key_files=["pyproject.toml", "package.json"],
            file_count=7,
        ),
        detected_stack=DetectedStackSummary(
            frameworks=["fastapi", "react"],
            languages=["python", "typescript"],
        ),
        backend_summary=BackendSummary(
            routes=[BackendRouteSummary(method="GET", path="/health", source_file="app/main.py")]
        ),
        frontend_summary=FrontendSummary(
            framework="react",
            bundler="vite",
            state_manager=None,
            routing=[FrontendRouteSummary(path="/", source_file="web/App.tsx")],
            api_calls=[FrontendApiCallSummary(url="/health", source_file="web/App.tsx", client="fetch", method="GET")],
            state_units=[FrontendStateUnitSummary(name="session", kind="context", source_file="web/App.tsx")],
            components=[FrontendComponentSummary(name="App", source_file="web/App.tsx", imports=["react-router-dom"])],
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
            request_lifecycle=["Browser submits a request.", "FastAPI handles the request.", "UI renders the response."],
            run_steps=["Install dependencies", "Start the API", "Open the app"],
            pitfalls=["Missing environment variables"],
            next_steps=["Trace a single route end to end."],
            self_check_questions=["Which route serves health?"],
            faq_entries=[TutorialFaqEntry(question="Where do I start?", answer="Start with app/main.py.")],
            code_walkthroughs=[
                TutorialCodeWalkthrough(
                    title="Health route walkthrough",
                    source_file="app/main.py",
                    snippet="@app.get('/health')",
                    notes=["This route exposes the health endpoint."],
                )
            ],
        ),
        deploy_summary=DeploySummary(
            services=[DeployServiceSummary(name="api", source_file="docker-compose.yml", ports=["8000:8000"], depends_on=["redis"])],
            environment_files=[".env.example"],
            manifests=["docker-compose.yml"],
            environment_variables=[EnvironmentVariableSummary(key="REDIS_URL", source_file=".env.example")],
            kubernetes_resources=[KubernetesResourceSummary(kind="Deployment", name="api", source_file="k8s/api.yaml")],
        ),
        critique_summary=CritiqueSummary(
            coverage_notes=["Backend routes were detected."],
            inferred_sections=["Frontend component boundaries were inferred from imports."],
            missing_areas=["No real PDF artifact was generated."],
        ),
        mermaid_sections=MermaidSections(system="graph TD\n  A[Client] --> B[API]"),
    )
