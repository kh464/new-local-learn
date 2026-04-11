import json
from pathlib import Path

import pytest

from app.core.models import TaskStage, TaskState
from app.tasks.jobs import run_analysis_job
from app.tasks import worker as worker_module
from app.tasks.worker import startup


async def test_run_analysis_job_sets_succeeded(fake_job_context):
    store = fake_job_context["task_store"]
    seen_statuses = []
    original_set_status = store.set_status

    async def set_status_spy(status):
        seen_statuses.append(status)
        await original_set_status(status)

    store.set_status = set_status_spy
    github_url = "https://github.com/octocat/Hello-World"
    result = await run_analysis_job(fake_job_context, "task-1", github_url)

    assert result["task_id"] == "task-1"
    assert result["state"] == TaskState.SUCCEEDED.value
    assert [status.stage for status in seen_statuses] == [
        TaskStage.FETCH_REPO,
        TaskStage.SCAN_TREE,
        TaskStage.DETECT_STACK,
        TaskStage.ANALYZE_BACKEND,
        TaskStage.ANALYZE_FRONTEND,
        TaskStage.BUILD_DOC,
        TaskStage.BUILD_KNOWLEDGE,
        TaskStage.FINALIZE,
    ]
    assert [status.progress for status in seen_statuses] == [5, 20, 35, 50, 65, 85, 95, 100]
    assert seen_statuses[0].created_at == seen_statuses[1].created_at

    status = await store.get_status("task-1")
    assert status is not None
    assert status.state is TaskState.SUCCEEDED
    assert status.stage is TaskStage.FINALIZE
    assert status.progress == 100
    assert status.knowledge_state.value == "ready"

    result_payload = await store.get_result("task-1")
    assert result_payload.github_url == github_url
    assert result_payload.markdown_path.endswith("result.md")
    assert result_payload.html_path.endswith("result.html")
    assert result_payload.pdf_path.endswith("result.pdf")
    assert Path(result_payload.html_path).is_file()
    assert Path(result_payload.pdf_path).is_file()
    assert result_payload.repo_summary.key_files == ["package.json", "pyproject.toml"]
    assert "fastapi" in result_payload.detected_stack.frameworks
    assert "react" in result_payload.detected_stack.frameworks
    assert result_payload.backend_summary.routes[0].path == "/health"
    assert result_payload.frontend_summary.api_calls[0].url == "/health"
    assert result_payload.frontend_summary.framework == "react"
    assert result_payload.frontend_summary.components[0].name == "App"
    assert result_payload.logic_summary.flows[0].backend_route == "/health"
    assert result_payload.tutorial_summary.run_steps
    assert result_payload.tutorial_summary.request_lifecycle
    assert result_payload.tutorial_summary.code_walkthroughs
    assert result_payload.agent_metadata is not None
    assert result_payload.agent_metadata.enabled is True
    assert set(result_payload.agent_metadata.used_roles) >= {
        "stack-detector",
        "backend-analyzer",
        "frontend-analyzer",
        "deploy-analyzer",
        "logic-mapper",
        "critic",
        "tutor",
    }
    assert result_payload.agent_metadata.fallbacks == []
    nodes_by_name = {node.node: node for node in result_payload.agent_metadata.execution_nodes}
    assert nodes_by_name["logic_mapping"].depends_on == ["backend_analysis", "frontend_analysis"]
    assert nodes_by_name["tutorial_generation"].depends_on == ["logic_mapping"]
    assert all(node.status == "completed" for node in nodes_by_name.values())
    assert result_payload.deploy_summary.environment_files == [".env.example"]
    assert [service.name for service in result_payload.deploy_summary.services] == ["redis", "api"]
    assert result_payload.critique_summary.coverage_notes
    assert "React UI" in result_payload.mermaid_sections.system

    events = await store.get_events("task-1")
    assert [event["stage"] for event in events] == [
        TaskStage.FETCH_REPO.value,
        TaskStage.SCAN_TREE.value,
        TaskStage.DETECT_STACK.value,
        TaskStage.ANALYZE_BACKEND.value,
        TaskStage.ANALYZE_FRONTEND.value,
        TaskStage.BUILD_DOC.value,
        TaskStage.BUILD_KNOWLEDGE.value,
        TaskStage.FINALIZE.value,
    ]
    assert [event["progress"] for event in events] == [5, 20, 35, 50, 65, 85, 95, 100]
    assert [event["state"] for event in events[:-1]] == [TaskState.RUNNING.value] * 7
    assert events[-1]["state"] == TaskState.SUCCEEDED.value
    metrics = await store.get_metrics_snapshot()
    assert metrics["analysis_jobs_succeeded_total"] == 1


async def test_run_analysis_job_builds_knowledge_after_docs(fake_job_context):
    store = fake_job_context["task_store"]
    seen_statuses = []
    original_set_status = store.set_status
    captured: dict[str, object] = {}
    repo_map_captured: dict[str, object] = {}

    async def set_status_spy(status):
        seen_statuses.append(status)
        await original_set_status(status)

    class FakeKnowledgeBuilder:
        def build(self, *, task_id: str, repo_path, db_path):
            captured["task_id"] = task_id
            captured["repo_path"] = Path(repo_path)
            captured["db_path"] = Path(db_path)
            Path(db_path).write_bytes(b"sqlite")
            return {"indexed_documents": 3, "indexed_chunks": 4}

    class FakeRepoMapBuilder:
        def build(self, *, task_id: str, repo_path, output_path):
            repo_map_captured["task_id"] = task_id
            repo_map_captured["repo_path"] = Path(repo_path)
            repo_map_captured["output_path"] = Path(output_path)
            Path(output_path).write_text('{"task_id":"task-knowledge-ready"}', encoding="utf-8")
            return {"task_id": task_id}

    fake_job_context["knowledge_builder"] = FakeKnowledgeBuilder()
    fake_job_context["repo_map_builder"] = FakeRepoMapBuilder()
    store.set_status = set_status_spy

    result = await run_analysis_job(fake_job_context, "task-knowledge-ready", "https://github.com/octocat/Hello-World")

    assert result["state"] == TaskState.SUCCEEDED.value
    assert [status.stage for status in seen_statuses] == [
        TaskStage.FETCH_REPO,
        TaskStage.SCAN_TREE,
        TaskStage.DETECT_STACK,
        TaskStage.ANALYZE_BACKEND,
        TaskStage.ANALYZE_FRONTEND,
        TaskStage.BUILD_DOC,
        TaskStage.BUILD_KNOWLEDGE,
        TaskStage.FINALIZE,
    ]
    assert [status.progress for status in seen_statuses] == [5, 20, 35, 50, 65, 85, 95, 100]
    assert seen_statuses[6].knowledge_state.value == "running"
    assert seen_statuses[7].knowledge_state.value == "ready"
    assert captured["task_id"] == "task-knowledge-ready"
    assert captured["repo_path"].is_dir() is True
    assert captured["db_path"].name == "knowledge.db"
    assert captured["db_path"].is_file() is True
    assert repo_map_captured["task_id"] == "task-knowledge-ready"
    assert repo_map_captured["repo_path"].is_dir() is True
    assert repo_map_captured["output_path"].name == "repo_map.json"
    assert repo_map_captured["output_path"].is_file() is True

    final_status = await store.get_status("task-knowledge-ready")
    assert final_status is not None
    assert final_status.state is TaskState.SUCCEEDED
    assert final_status.knowledge_state.value == "ready"
    assert final_status.knowledge_error is None


async def test_run_analysis_job_builds_code_graph_after_knowledge(fake_job_context):
    captured: dict[str, object] = {}

    class FakeCodeGraphBuilder:
        def build(self, *, task_id: str, repo_root, db_path):
            captured["task_id"] = task_id
            captured["repo_root"] = Path(repo_root)
            captured["db_path"] = Path(db_path)
            return {
                "files_count": 2,
                "symbols_count": 3,
                "edges_count": 4,
                "unresolved_calls_count": 1,
                "skipped_paths": [],
            }

    fake_job_context["code_graph_builder"] = FakeCodeGraphBuilder()

    result = await run_analysis_job(fake_job_context, "task-code-graph-ready", "https://github.com/octocat/Hello-World")

    assert result["state"] == TaskState.SUCCEEDED.value
    assert captured["task_id"] == "task-code-graph-ready"
    assert captured["repo_root"].is_dir() is True
    assert captured["db_path"].name == "knowledge.db"
    assert captured["db_path"].is_file() is True


async def test_run_analysis_job_builds_embedding_index_after_code_graph(fake_job_context):
    captured: dict[str, object] = {}

    class FakeEmbeddingIndexBuilder:
        async def build(self, *, task_id: str, db_path):
            captured["task_id"] = task_id
            captured["db_path"] = Path(db_path)
            return 5

    fake_job_context["embedding_index_builder"] = FakeEmbeddingIndexBuilder()

    result = await run_analysis_job(fake_job_context, "task-embedding-ready", "https://github.com/octocat/Hello-World")

    assert result["state"] == TaskState.SUCCEEDED.value
    assert captured["task_id"] == "task-embedding-ready"
    assert captured["db_path"].name == "knowledge.db"
    assert captured["db_path"].is_file() is True


async def test_run_analysis_job_keeps_result_when_knowledge_build_fails(fake_job_context):
    class FailingKnowledgeBuilder:
        def build(self, *, task_id: str, repo_path, db_path):
            raise RuntimeError("knowledge sqlite locked")

    fake_job_context["knowledge_builder"] = FailingKnowledgeBuilder()

    result = await run_analysis_job(fake_job_context, "task-knowledge-failed", "https://github.com/octocat/Hello-World")

    assert result["state"] == TaskState.SUCCEEDED.value
    store = fake_job_context["task_store"]
    payload = await store.get_result("task-knowledge-failed")
    assert payload is not None

    final_status = await store.get_status("task-knowledge-failed")
    assert final_status is not None
    assert final_status.state is TaskState.SUCCEEDED
    assert final_status.stage is TaskStage.FINALIZE
    assert final_status.knowledge_state.value == "failed"
    assert final_status.knowledge_error == "knowledge sqlite locked"

    events = await store.get_events("task-knowledge-failed")
    assert events[-2]["stage"] == TaskStage.BUILD_KNOWLEDGE.value
    assert events[-2]["progress"] == 95
    assert events[-1]["state"] == TaskState.SUCCEEDED.value


async def test_run_analysis_job_prefers_configured_tutorial_generator(fake_job_context):
    async def tutorial_generator(**kwargs):
        assert kwargs["repo_summary"]["file_count"] == 7
        return {
            "mental_model": "LLM mental model",
            "run_steps": ["Inspect the generated overview first."],
            "pitfalls": ["Do not ignore the routing summary."],
            "self_check_questions": ["Which API call crosses into the backend?"],
        }

    fake_job_context["tutorial_generator"] = tutorial_generator
    result = await run_analysis_job(fake_job_context, "task-llm", "https://github.com/octocat/Hello-World")

    assert result["state"] == TaskState.SUCCEEDED.value
    store = fake_job_context["task_store"]
    payload = await store.get_result("task-llm")
    assert payload is not None
    assert payload.tutorial_summary.mental_model == "LLM mental model"
    assert payload.tutorial_summary.run_steps == ["Inspect the generated overview first."]
    assert payload.agent_metadata is not None
    nodes_by_name = {node.node: node for node in payload.agent_metadata.execution_nodes}
    assert nodes_by_name["tutorial_generation"].execution_mode == "llm"
    assert payload.agent_metadata.fallbacks == []


async def test_run_analysis_job_falls_back_when_tutorial_generator_errors(fake_job_context):
    async def tutorial_generator(**kwargs):
        raise RuntimeError("provider timeout")

    fake_job_context["tutorial_generator"] = tutorial_generator
    result = await run_analysis_job(fake_job_context, "task-llm-fallback", "https://github.com/octocat/Hello-World")

    assert result["state"] == TaskState.SUCCEEDED.value
    store = fake_job_context["task_store"]
    payload = await store.get_result("task-llm-fallback")
    assert payload is not None
    assert payload.tutorial_summary.mental_model != "LLM mental model"
    assert payload.tutorial_summary.run_steps
    assert payload.agent_metadata is not None
    assert "tutorial_generation" in payload.agent_metadata.fallbacks
    nodes_by_name = {node.node: node for node in payload.agent_metadata.execution_nodes}
    assert nodes_by_name["tutorial_generation"].status == "fallback"


async def test_worker_startup_registers_runtime_dependencies(fakeredis_client):
    ctx = {"redis": fakeredis_client}

    await startup(ctx)

    assert "settings" in ctx
    assert "task_store" in ctx
    assert callable(ctx["clone_repo"])
    assert callable(ctx["read_files"])
    assert hasattr(ctx["knowledge_builder"], "build")
    assert hasattr(ctx["code_graph_builder"], "build")
    assert hasattr(ctx["repo_map_builder"], "build")


async def test_worker_startup_clone_repo_uses_configured_timeout(fakeredis_client, monkeypatch):
    captured: dict[str, object] = {}

    async def fake_clone_github_repo(github_url: str, destination, *, timeout_seconds: int):
        captured["github_url"] = github_url
        captured["destination"] = destination
        captured["timeout_seconds"] = timeout_seconds
        return destination

    monkeypatch.setattr(worker_module, "clone_github_repo", fake_clone_github_repo)
    original_timeout = worker_module.settings.clone_timeout_seconds
    worker_module.settings.clone_timeout_seconds = 12
    ctx = {"redis": fakeredis_client}

    try:
        await startup(ctx)
        await ctx["clone_repo"]("https://github.com/octocat/Hello-World", "repo-dir")
    finally:
        worker_module.settings.clone_timeout_seconds = original_timeout

    assert captured["github_url"] == "https://github.com/octocat/Hello-World"
    assert captured["destination"] == "repo-dir"
    assert captured["timeout_seconds"] == 12


async def test_worker_startup_registers_embedding_index_builder_when_vector_store_enabled(fakeredis_client, tmp_path, monkeypatch):
    config_path = tmp_path / "llm.yaml"
    config_path.write_text(
        """
version: 1
llm:
  default_profile: chat
  timeout_seconds: 45
  max_retries: 1
  providers:
    demo:
      enabled: true
      base_url: https://example.test/v1
      api_key: secret-token
  routing:
    profiles:
      chat:
        provider: demo
        model: demo-chat-model
""".strip(),
        encoding="utf-8",
    )

    original_enabled = worker_module.settings.llm_enabled
    original_config_path = worker_module.settings.llm_config_path
    original_vector_enabled = getattr(worker_module.settings, "vector_store_enabled", False)
    original_vector_url = getattr(worker_module.settings, "vector_store_url", "http://localhost:6333")
    original_vector_api_key = getattr(worker_module.settings, "vector_store_api_key", None)
    original_embedding_model = getattr(worker_module.settings, "embedding_model", "text-embedding-3-small")

    try:
        worker_module.settings.llm_enabled = True
        worker_module.settings.llm_config_path = config_path
        worker_module.settings.vector_store_enabled = True
        worker_module.settings.vector_store_url = "https://qdrant.test"
        worker_module.settings.vector_store_api_key = "qdrant-secret"
        worker_module.settings.embedding_model = "demo-embed-model"

        ctx = {"redis": fakeredis_client}
        await startup(ctx)

        assert hasattr(ctx["embedding_index_builder"], "build")
    finally:
        worker_module.settings.llm_enabled = original_enabled
        worker_module.settings.llm_config_path = original_config_path
        worker_module.settings.vector_store_enabled = original_vector_enabled
        worker_module.settings.vector_store_url = original_vector_url
        worker_module.settings.vector_store_api_key = original_vector_api_key
        worker_module.settings.embedding_model = original_embedding_model


async def test_worker_startup_registers_tutorial_generator_when_llm_is_configured(
    fakeredis_client,
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "llm.yaml"
    config_path.write_text(
        """
version: 1
llm:
  default_provider: demo
  default_profile: chat
  providers:
    demo:
      enabled: true
      base_url: https://example.test/v1
      api_key: secret-token
  routing:
    profiles:
      chat:
        provider: demo
        model: demo-model
""".strip(),
        encoding="utf-8",
    )
    original_enabled = getattr(worker_module.settings, "llm_enabled", None)
    original_config_path = getattr(worker_module.settings, "llm_config_path", None)
    ctx = {"redis": fakeredis_client}

    try:
        worker_module.settings.llm_enabled = True
        worker_module.settings.llm_config_path = config_path
        await startup(ctx)
    finally:
        if original_enabled is not None:
            worker_module.settings.llm_enabled = original_enabled
        if original_config_path is not None:
            worker_module.settings.llm_config_path = original_config_path

    assert callable(ctx["tutorial_generator"])


def test_worker_settings_use_configured_limits():
    assert worker_module.WorkerSettings.job_timeout == worker_module.settings.worker_job_timeout_seconds
    assert worker_module.WorkerSettings.max_jobs == worker_module.settings.worker_max_jobs


async def test_run_analysis_job_emits_structured_logs(fake_job_context, caplog):
    caplog.set_level("INFO", logger="app.tasks")

    result = await run_analysis_job(fake_job_context, "task-logs", "https://github.com/octocat/Hello-World")

    assert result["state"] == TaskState.SUCCEEDED.value
    records = [json.loads(record.message) for record in caplog.records if record.name == "app.tasks"]
    assert records[0]["task_id"] == "task-logs"
    assert records[0]["stage"] == TaskStage.FETCH_REPO.value
    assert records[-1]["state"] == TaskState.SUCCEEDED.value
    assert records[-1]["stage"] == TaskStage.FINALIZE.value


async def test_run_analysis_job_marks_failed_on_error(fake_job_context):
    store = fake_job_context["task_store"]
    seen_statuses = []
    original_set_status = store.set_status

    async def set_status_spy(status):
        seen_statuses.append(status)
        await original_set_status(status)

    async def set_result_fail(task_id, result):
        raise RuntimeError("boom")

    store.set_status = set_status_spy
    store.set_result = set_result_fail
    github_url = "https://github.com/octocat/Hello-World"

    result = await run_analysis_job(fake_job_context, "task-2", github_url)

    assert result["task_id"] == "task-2"
    assert result["state"] == TaskState.FAILED.value
    assert [status.stage for status in seen_statuses[:-1]] == [
        TaskStage.FETCH_REPO,
        TaskStage.SCAN_TREE,
        TaskStage.DETECT_STACK,
        TaskStage.ANALYZE_BACKEND,
        TaskStage.ANALYZE_FRONTEND,
        TaskStage.BUILD_DOC,
    ]
    assert seen_statuses[-1].stage is TaskStage.FINALIZE
    assert seen_statuses[0].created_at == seen_statuses[1].created_at

    status = await store.get_status("task-2")
    assert status is not None
    assert status.state is TaskState.FAILED
    assert status.stage is TaskStage.FINALIZE
    assert status.progress == 100
    assert status.error == "boom"

    result_payload = await store.get_result("task-2")
    assert result_payload is None

    events = await store.get_events("task-2")
    assert [event["stage"] for event in events[:-1]] == [
        TaskStage.FETCH_REPO.value,
        TaskStage.SCAN_TREE.value,
        TaskStage.DETECT_STACK.value,
        TaskStage.ANALYZE_BACKEND.value,
        TaskStage.ANALYZE_FRONTEND.value,
        TaskStage.BUILD_DOC.value,
    ]
    assert events[-1] == {
        "state": TaskState.FAILED.value,
        "stage": TaskStage.FINALIZE.value,
        "progress": 100,
        "error": "boom",
    }
    metrics = await store.get_metrics_snapshot()
    assert metrics["analysis_jobs_failed_total"] == 1


async def test_run_analysis_job_marks_failed_when_repository_exceeds_scan_limits(fake_job_context):
    fake_job_context["settings"].max_file_count = 1
    fake_job_context["settings"].max_total_bytes = 100

    result = await run_analysis_job(fake_job_context, "task-too-large", "https://github.com/octocat/Hello-World")

    assert result["task_id"] == "task-too-large"
    assert result["state"] == TaskState.FAILED.value
    store = fake_job_context["task_store"]
    status = await store.get_status("task-too-large")
    assert status is not None
    assert status.state is TaskState.FAILED
    assert "Repository exceeds file count limit" in (status.error or "")


async def test_run_analysis_job_marks_cancelled_when_cancel_requested_before_start(fake_job_context):
    store = fake_job_context["task_store"]
    await store.request_task_cancel("task-cancelled")

    result = await run_analysis_job(fake_job_context, "task-cancelled", "https://github.com/octocat/Hello-World")

    assert result["task_id"] == "task-cancelled"
    assert result["state"] == TaskState.CANCELLED.value
    status = await store.get_status("task-cancelled")
    assert status is not None
    assert status.state is TaskState.CANCELLED
    assert status.stage is TaskStage.FETCH_REPO

    events = await store.get_events("task-cancelled")
    assert events[-1] == {
        "state": TaskState.CANCELLED.value,
        "stage": TaskStage.FETCH_REPO.value,
        "progress": 0,
        "message": "Cancellation requested.",
    }
