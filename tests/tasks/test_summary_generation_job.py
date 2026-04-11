from __future__ import annotations

from pathlib import Path

import pytest

from app.core.models import TaskState
from app.tasks.jobs import run_analysis_job
from app.tasks.worker import startup


@pytest.mark.asyncio
async def test_run_analysis_job_builds_summaries_after_code_graph(fake_job_context):
    sequence: list[str] = []
    captured: dict[str, object] = {}

    class FakeKnowledgeBuilder:
        def build(self, *, task_id: str, repo_path, db_path):
            Path(db_path).write_bytes(b"sqlite")
            sequence.append("knowledge")
            return {"indexed_documents": 1}

    class FakeCodeGraphBuilder:
        def build(self, *, task_id: str, repo_root, db_path):
            sequence.append("graph")
            return {"files_count": 1}

    class FakeSummaryGenerationBuilder:
        async def build(self, *, task_id: str, db_path, repo_root):
            sequence.append("summary")
            captured["task_id"] = task_id
            captured["db_path"] = str(db_path)
            captured["repo_root"] = str(repo_root)

    class FakeEmbeddingIndexBuilder:
        async def build(self, *, task_id: str, db_path):
            sequence.append("embedding")
            return None

    fake_job_context["knowledge_builder"] = FakeKnowledgeBuilder()
    fake_job_context["code_graph_builder"] = FakeCodeGraphBuilder()
    fake_job_context["summary_generation_builder"] = FakeSummaryGenerationBuilder()
    fake_job_context["embedding_index_builder"] = FakeEmbeddingIndexBuilder()

    result = await run_analysis_job(
        fake_job_context,
        "task-summary-ready",
        "https://github.com/octocat/Hello-World",
    )

    assert result["state"] == TaskState.SUCCEEDED.value
    assert captured["task_id"] == "task-summary-ready"
    assert captured["db_path"].endswith("knowledge.db")
    assert Path(captured["repo_root"]).is_dir() is True
    assert sequence == ["knowledge", "graph", "summary", "embedding"]


@pytest.mark.asyncio
async def test_worker_startup_registers_summary_generation_builder(fakeredis_client):
    ctx = {"redis": fakeredis_client}

    await startup(ctx)

    assert "summary_generation_builder" in ctx
    assert hasattr(ctx["summary_generation_builder"], "build")
