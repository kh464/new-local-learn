from __future__ import annotations

import pytest

from app.core.models import AnalysisResult, TaskKnowledgeState, TaskState, TaskStatus
from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode
from app.services.code_graph.storage import CodeGraphStore
from app.storage.artifacts import ArtifactPaths
from app.storage.task_store import RedisTaskStore


def _seed_graph(*, task_id: str, knowledge_db_path) -> None:
    graph_store = CodeGraphStore(knowledge_db_path)
    graph_store.initialize()
    graph_store.upsert_files(
        [
            CodeFileNode(
                task_id=task_id,
                path="app/main.py",
                language="python",
                file_kind="entrypoint",
                summary_zh="应用入口文件。",
                entry_role="backend_entry",
            ),
            CodeFileNode(
                task_id=task_id,
                path="app/services/health.py",
                language="python",
                file_kind="module",
                summary_zh="健康检查服务模块。",
            ),
        ]
    )
    graph_store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id=task_id,
                symbol_id="function:python:app/main.py:app.main.health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=6,
                end_line=8,
                summary_zh="健康检查路由处理函数。",
            ),
            CodeSymbolNode(
                task_id=task_id,
                symbol_id="function:python:app/services/health.py:app.services.health.build_payload",
                symbol_kind="function",
                name="build_payload",
                qualified_name="app.services.health.build_payload",
                file_path="app/services/health.py",
                start_line=3,
                end_line=5,
                summary_zh="构建健康检查响应。",
            ),
        ]
    )
    graph_store.insert_edges(
        [
            CodeEdge(
                task_id=task_id,
                from_symbol_id="function:python:app/main.py:app.main.health",
                to_symbol_id="function:python:app/services/health.py:app.services.health.build_payload",
                edge_kind="calls",
                source_path="app/main.py",
                line=7,
                confidence=1.0,
            )
        ]
    )


@pytest.mark.asyncio
async def test_graph_api_returns_repository_subgraph(
    api_client,
    fakeredis_client,
    sample_analysis_result: AnalysisResult,
):
    task_id = "task-graph-api"
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(
        TaskStatus(
            task_id=task_id,
            state=TaskState.SUCCEEDED,
            progress=100,
            knowledge_state=TaskKnowledgeState.READY,
        )
    )
    await store.set_result(task_id, sample_analysis_result)
    api_client._transport.app.state.task_store = store

    artifacts = ArtifactPaths(
        base_dir=api_client._transport.app.state.settings.artifacts_dir,
        task_id=task_id,
    )
    artifacts.task_dir.mkdir(parents=True, exist_ok=True)
    _seed_graph(task_id=task_id, knowledge_db_path=artifacts.knowledge_db_path)

    response = await api_client.get(f"/api/v1/tasks/{task_id}/graph?view=repository")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == task_id
    assert payload["view"] == "repository"
    assert payload["nodes"]
    assert payload["edges"]
    assert any(node["node_id"] == "file:app/main.py" for node in payload["nodes"])
    assert any(
        node["node_id"] == "function:python:app/main.py:app.main.health"
        for node in payload["nodes"]
    )
    assert any(edge["kind"] == "contains" for edge in payload["edges"])
    assert any(edge["kind"] == "calls" for edge in payload["edges"])


@pytest.mark.asyncio
async def test_graph_api_returns_symbol_focus_subgraph(
    api_client,
    fakeredis_client,
    sample_analysis_result: AnalysisResult,
):
    task_id = "task-graph-symbol"
    focus_symbol_id = "function:python:app/main.py:app.main.health"
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(
        TaskStatus(
            task_id=task_id,
            state=TaskState.SUCCEEDED,
            progress=100,
            knowledge_state=TaskKnowledgeState.READY,
        )
    )
    await store.set_result(task_id, sample_analysis_result)
    api_client._transport.app.state.task_store = store

    artifacts = ArtifactPaths(
        base_dir=api_client._transport.app.state.settings.artifacts_dir,
        task_id=task_id,
    )
    artifacts.task_dir.mkdir(parents=True, exist_ok=True)
    _seed_graph(task_id=task_id, knowledge_db_path=artifacts.knowledge_db_path)

    response = await api_client.get(
        f"/api/v1/tasks/{task_id}/graph",
        params={"view": "symbol", "symbol_id": focus_symbol_id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["view"] == "symbol"
    assert payload["focus_node_id"] == focus_symbol_id
    assert any(node["node_id"] == focus_symbol_id for node in payload["nodes"])
    assert any(
        node["node_id"] == "function:python:app/services/health.py:app.services.health.build_payload"
        for node in payload["nodes"]
    )
    assert any(edge["kind"] == "calls" for edge in payload["edges"])
