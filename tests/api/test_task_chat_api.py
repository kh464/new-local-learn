from __future__ import annotations

import sqlite3

import pytest

from app.core.models import (
    AnalysisResult,
    PlannerMetadata,
    TaskChatCitation,
    TaskChatMessage,
    TaskChatResponse,
    TaskGraphEvidence,
    TaskKnowledgeState,
    TaskState,
    TaskStatus,
)
from app.storage.artifacts import ArtifactPaths
from app.storage.task_store import RedisTaskStore


@pytest.mark.asyncio
async def test_task_chat_endpoint_returns_graph_evidence_for_ready_task(
    api_client,
    fakeredis_client,
    sample_analysis_result: AnalysisResult,
):
    class FakeKnowledgeChatService:
        async def answer_question(
            self,
            *,
            task_id: str,
            db_path,
            repo_map_path,
            question: str,
            history: list[TaskChatMessage],
        ):
            assert task_id == "task-chat-api"
            assert db_path.name == "knowledge.db"
            assert repo_map_path.name == "repo_map.json"
            assert history == []
            assert question == "鍓嶇璇锋眰濡備綍鍒板悗绔紵"
            return TaskChatResponse(
                answer="鍓嶇浼氬湪 web/App.tsx 鍙戣捣 /health 璇锋眰锛岄殢鍚庤繘鍏 app/main.py 閲岀殑 FastAPI 璺敱銆",
                citations=[
                    TaskChatCitation(
                        path="app/main.py",
                        start_line=1,
                        end_line=8,
                        reason="杩欓噷鍒濆鍖栦簡 FastAPI 搴旂敤骞跺０鏄庝簡 /health 璺敱銆",
                        snippet="from fastapi import FastAPI",
                    )
                ],
                graph_evidence=[
                    TaskGraphEvidence(kind="entrypoint", label="鍚庣鍏ュ彛", path="app/main.py"),
                    TaskGraphEvidence(kind="call_chain", label="web/App.tsx -> GET /health -> app/main.py:health"),
                ],
                supplemental_notes=[],
                confidence="high",
                answer_source="llm",
                planner_metadata=PlannerMetadata(
                    planning_source="llm",
                    loop_count=2,
                    used_tools=["trace_call_chain", "open_file"],
                    fallback_used=False,
                    search_queries=["health", "app/main.py"],
                ),
            )

    store = RedisTaskStore(fakeredis_client)
    await store.set_status(
        TaskStatus(
            task_id="task-chat-api",
            state=TaskState.SUCCEEDED,
            progress=100,
            knowledge_state=TaskKnowledgeState.READY,
        )
    )
    await store.set_result("task-chat-api", sample_analysis_result)
    api_client._transport.app.state.task_store = store
    api_client._transport.app.state.knowledge_chat_service = FakeKnowledgeChatService()

    artifacts = ArtifactPaths(
        base_dir=api_client._transport.app.state.settings.artifacts_dir,
        task_id="task-chat-api",
    )
    artifacts.task_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(artifacts.knowledge_db_path):
        pass
    artifacts.repo_map_path.write_text('{"task_id":"task-chat-api"}', encoding="utf-8")

    response = await api_client.post(
        "/api/v1/tasks/task-chat-api/chat",
        json={"question": "鍓嶇璇锋眰濡備綍鍒板悗绔紵"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_message"]["citations"][0]["path"] == "app/main.py"
    assert payload["assistant_message"]["graph_evidence"][0]["kind"] == "entrypoint"
    assert payload["assistant_message"]["graph_evidence"][1]["kind"] == "call_chain"
    assert payload["assistant_message"]["answer_source"] == "llm"
    assert payload["assistant_message"]["planner_metadata"]["planning_source"] == "llm"
    assert payload["assistant_message"]["planner_metadata"]["loop_count"] == 2
    assert payload["assistant_message"]["planner_metadata"]["used_tools"] == ["trace_call_chain", "open_file"]
    assert payload["assistant_message"]["planner_metadata"]["search_queries"] == ["health", "app/main.py"]

    history_response = await api_client.get("/api/v1/tasks/task-chat-api/chat/messages")
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert len(history_payload["messages"]) == 2
    assert history_payload["messages"][0]["role"] == "user"
    assert history_payload["messages"][1]["role"] == "assistant"
    assert history_payload["messages"][1]["graph_evidence"][0]["kind"] == "entrypoint"
    assert history_payload["messages"][1]["planner_metadata"]["planning_source"] == "llm"
    assert history_payload["messages"][1]["planner_metadata"]["search_queries"] == ["health", "app/main.py"]


@pytest.mark.asyncio
async def test_task_chat_endpoint_rejects_tasks_without_ready_knowledge(api_client, fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(
        TaskStatus(
            task_id="task-chat-running",
            state=TaskState.SUCCEEDED,
            progress=100,
            knowledge_state=TaskKnowledgeState.RUNNING,
        )
    )
    api_client._transport.app.state.task_store = store

    response = await api_client.post(
        "/api/v1/tasks/task-chat-running/chat",
        json={"question": "鐜板湪鍙互寮€濮嬫彁闂簡鍚楋紵"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Task chat is available only after the knowledge base is ready."


@pytest.mark.asyncio
async def test_task_chat_endpoint_rejects_blank_question(
    api_client,
    fakeredis_client,
    sample_analysis_result: AnalysisResult,
):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(
        TaskStatus(
            task_id="task-chat-blank",
            state=TaskState.SUCCEEDED,
            progress=100,
            knowledge_state=TaskKnowledgeState.READY,
        )
    )
    await store.set_result("task-chat-blank", sample_analysis_result)
    api_client._transport.app.state.task_store = store

    artifacts = ArtifactPaths(
        base_dir=api_client._transport.app.state.settings.artifacts_dir,
        task_id="task-chat-blank",
    )
    artifacts.task_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(artifacts.knowledge_db_path):
        pass
    artifacts.repo_map_path.write_text('{"task_id":"task-chat-blank"}', encoding="utf-8")

    response = await api_client.post(
        "/api/v1/tasks/task-chat-blank/chat",
        json={"question": "   "},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_task_chat_endpoint_uses_default_orchestrator_first_service(
    api_client,
    fakeredis_client,
    sample_analysis_result: AnalysisResult,
):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(
        TaskStatus(
            task_id="task-chat-default",
            state=TaskState.SUCCEEDED,
            progress=100,
            knowledge_state=TaskKnowledgeState.READY,
        )
    )
    await store.set_result("task-chat-default", sample_analysis_result)

    app = api_client._transport.app
    app.state.task_store = store
    app.state.settings.llm_enabled = False
    if hasattr(app.state, "knowledge_chat_service"):
        delattr(app.state, "knowledge_chat_service")
    if hasattr(app.state, "task_chat_orchestrator"):
        delattr(app.state, "task_chat_orchestrator")

    artifacts = ArtifactPaths(
        base_dir=app.state.settings.artifacts_dir,
        task_id="task-chat-default",
    )
    artifacts.task_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(artifacts.knowledge_db_path):
        pass
    artifacts.repo_map_path.write_text(
        """
        {
          "task_id": "task-chat-default",
          "entrypoints": {
            "backend": {"file_path": "app/main.py", "language": "python", "layer": "backend"},
            "frontend": {"file_path": "web/App.tsx", "language": "typescript", "layer": "frontend"}
          },
          "symbol_nodes": [
            {
              "id": "symbol:app/main.py:health",
              "file_path": "app/main.py",
              "name": "health",
              "kind": "function",
              "line": 4
            }
          ],
          "edges": [],
          "call_chains": [
            {
              "summary": "web/App.tsx -> GET /health -> app/main.py:health",
              "frontend_file": "web/App.tsx",
              "backend_file": "app/main.py",
              "route_path": "/health",
              "method": "GET"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    response = await api_client.post(
        "/api/v1/tasks/task-chat-default/chat",
        json={"question": "前端请求如何到后端？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_message"]["answer_source"] == "local"
    assert payload["assistant_message"]["planner_metadata"]["planning_source"] == "rule"
    assert payload["assistant_message"]["planner_metadata"]["loop_count"] >= 1
    assert payload["assistant_message"]["planner_metadata"]["used_tools"] == ["load_repo_map"]
    assert any(item["kind"] == "call_chain" for item in payload["assistant_message"]["graph_evidence"])
