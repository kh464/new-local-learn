from __future__ import annotations

import json
from json import JSONDecodeError

import pytest

from app.core.models import TaskChatMessage
from app.services.knowledge.retriever import KnowledgeRetriever
from app.services.llm.knowledge_chat import KnowledgeChatService
from app.storage.knowledge_store import KnowledgeChunkRecord, KnowledgeDocumentRecord, SQLiteKnowledgeStore


@pytest.mark.asyncio
async def test_knowledge_chat_service_delegates_to_orchestrator_when_present(tmp_path):
    captured: dict[str, object] = {}

    class StubOrchestrator:
        async def answer_question(self, **kwargs):
            captured.update(kwargs)
            from app.core.models import TaskChatResponse

            return TaskChatResponse(
                answer="delegated",
                citations=[],
                graph_evidence=[],
                supplemental_notes=[],
                confidence="high",
                answer_source="llm",
            )

    service = KnowledgeChatService(orchestrator=StubOrchestrator())
    response = await service.answer_question(
        task_id="task-wrap",
        db_path=tmp_path / "knowledge.db",
        repo_map_path=tmp_path / "repo_map.json",
        question="delegate me",
        history=[],
    )

    assert response.answer == "delegated"
    assert captured["task_id"] == "task-wrap"
    assert captured["question"] == "delegate me"


@pytest.mark.asyncio
async def test_knowledge_chat_service_builds_task_scoped_orchestrator_from_factory(tmp_path):
    captured: dict[str, object] = {}

    class StubOrchestrator:
        async def answer_question(self, **kwargs):
            captured["orchestrator_kwargs"] = kwargs
            from app.core.models import TaskChatResponse

            return TaskChatResponse(
                answer="factory-delegated",
                citations=[],
                graph_evidence=[],
                supplemental_notes=[],
                confidence="high",
                answer_source="llm",
            )

    async def orchestrator_factory(**kwargs):
        captured["factory_kwargs"] = kwargs
        return StubOrchestrator()

    service = KnowledgeChatService(orchestrator_factory=orchestrator_factory)
    response = await service.answer_question(
        task_id="task-factory",
        db_path=tmp_path / "knowledge.db",
        repo_map_path=tmp_path / "repo_map.json",
        question="factory delegate me",
        history=[],
    )

    assert response.answer == "factory-delegated"
    assert captured["factory_kwargs"]["task_id"] == "task-factory"
    assert captured["factory_kwargs"]["question"] == "factory delegate me"
    assert captured["orchestrator_kwargs"]["db_path"] == tmp_path / "knowledge.db"


@pytest.mark.asyncio
async def test_knowledge_chat_service_preserves_valid_json_prompt_under_size_pressure(tmp_path):
    db_path = _build_knowledge_db(tmp_path)
    repo_map_path = _build_repo_map(tmp_path)

    class StrictJsonClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            try:
                json.loads(user_prompt.split("\n", 1)[1])
            except (IndexError, JSONDecodeError) as exc:
                raise AssertionError("prompt JSON must remain valid") from exc
            return {
                "answer": "这是一个来自大模型的有效回答。",
                "supplemental_notes": [],
                "confidence": "high",
            }

    history = [
        TaskChatMessage(message_id=f"u-{index}", role="user", content=("很长的历史内容" * 40))
        for index in range(4)
    ]
    service = KnowledgeChatService(
        retriever=KnowledgeRetriever(),
        client=StrictJsonClient(),
        max_prompt_chars=120,
    )

    response = await service.answer_question(
        task_id="task-chat-1",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="前端请求如何到后端？",
        history=history,
    )

    assert response.answer_source == "llm"
    assert response.answer == "这是一个来自大模型的有效回答。"


@pytest.mark.asyncio
async def test_knowledge_chat_service_returns_graph_evidence_with_llm(tmp_path):
    db_path = _build_knowledge_db(tmp_path)
    repo_map_path = _build_repo_map(tmp_path)
    captured: dict[str, str] = {}

    class StubClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return {
                "answer": "后端入口在 app/main.py，前端请求会从 web/App.vue 发起，然后命中 app/main.py 里的 /health 路由。",
                "supplemental_notes": ["可以继续查看 web/App.vue 里的 fetch('/health') 调用。"],
                "confidence": "high",
            }

    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=StubClient())
    response = await service.answer_question(
        task_id="task-chat-1",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="前端请求如何到后端？",
        history=[TaskChatMessage(message_id="u-1", role="user", content="先看调用链")],
    )

    assert "前端请求" in response.answer
    assert response.citations
    assert response.citations[0].path == "web/App.vue"
    assert response.graph_evidence
    assert response.graph_evidence[0].kind == "entrypoint"
    assert any(item.kind == "call_chain" for item in response.graph_evidence)
    assert response.answer_source == "llm"
    assert "必须使用简体中文" in captured["system_prompt"]
    assert "graph_evidence" in captured["user_prompt"]
    assert "app/main.py" in captured["user_prompt"]


@pytest.mark.asyncio
async def test_knowledge_chat_service_falls_back_to_local_answer_with_graph_evidence(tmp_path):
    db_path = _build_knowledge_db(tmp_path)
    repo_map_path = _build_repo_map(tmp_path)

    class BrokenClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            raise RuntimeError("provider timeout")

    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=BrokenClient())
    response = await service.answer_question(
        task_id="task-chat-1",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="前端请求如何到后端？",
        history=[],
    )

    assert "先从 web/App.vue 发起" in response.answer
    assert "再进入 app/main.py" in response.answer
    assert response.citations
    assert response.graph_evidence
    assert any(item.kind == "call_chain" for item in response.graph_evidence)
    assert response.answer_source == "local"


@pytest.mark.asyncio
async def test_knowledge_chat_service_call_chain_mentions_frontend_handler(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)
    store.initialize()
    app_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-front-handler",
            path="app/api/routes.py",
            file_type="source",
            language="python",
            size_bytes=120,
            is_indexed=True,
        )
    )
    web_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-front-handler",
            path="web/src/App.vue",
            file_type="source",
            language="vue",
            size_bytes=140,
            is_indexed=True,
        )
    )
    store.insert_chunks(
        [
            KnowledgeChunkRecord(
                task_id="task-chat-front-handler",
                document_id=app_doc,
                chunk_index=0,
                path="app/api/routes.py",
                start_line=1,
                end_line=8,
                symbol_name="list_tasks",
                chunk_kind="function",
                content="@router.get('/tasks')\nasync def list_tasks():\n    return {'items': []}\n",
                summary="app/api/routes.py route list_tasks /tasks",
                token_estimate=20,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-front-handler",
                document_id=web_doc,
                chunk_index=0,
                path="web/src/App.vue",
                start_line=1,
                end_line=10,
                symbol_name="loadTasks",
                chunk_kind="function",
                content="<script setup>\nconst loadTasks = async () => fetch('/api/v1/tasks')\n</script>\n<template><button @click=\"loadTasks\">Load</button></template>\n",
                summary="web/src/App.vue loadTasks click fetch /api/v1/tasks",
                token_estimate=24,
            ),
        ]
    )
    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-chat-front-handler",
                "file_nodes": [],
                "symbol_nodes": [
                    {
                        "id": "symbol:app/api/routes.py:list_tasks",
                        "file_path": "app/api/routes.py",
                        "name": "list_tasks",
                        "kind": "function",
                        "line": 4,
                        "route_path": "/tasks",
                        "route_method": "GET",
                    },
                    {
                        "id": "symbol:web/src/App.vue:loadTasks",
                        "file_path": "web/src/App.vue",
                        "name": "loadTasks",
                        "kind": "function",
                        "line": 2,
                    },
                ],
                "edges": [
                    {
                        "type": "maps_to_backend",
                        "source": "symbol:web/src/App.vue:loadTasks",
                        "target": "symbol:app/api/routes.py:list_tasks",
                        "path": "/api/v1/tasks",
                        "method": "GET",
                        "frontend_file": "web/src/App.vue",
                        "frontend_symbol": "loadTasks",
                        "frontend_trigger": "click",
                        "backend_file": "app/api/routes.py",
                    }
                ],
                "entrypoints": {
                    "backend": {"file_path": "app/main.py", "language": "python", "layer": "backend"},
                    "frontend": {"file_path": "web/src/main.ts", "language": "typescript", "layer": "frontend"},
                },
                "call_chains": [
                    {
                        "summary": "web/src/App.vue:loadTasks [click] -> GET /api/v1/tasks -> app/api/routes.py:list_tasks",
                        "frontend_file": "web/src/App.vue",
                        "frontend_symbol": "loadTasks",
                        "frontend_trigger": "click",
                        "backend_file": "app/api/routes.py",
                        "route_path": "/api/v1/tasks",
                        "method": "GET",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=None)
    response = await service.answer_question(
        task_id="task-chat-front-handler",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="前端是哪个交互触发了这个请求？",
        history=[],
    )

    assert "前端入口函数 web/src/App.vue:loadTasks" in response.answer
    assert "由 click 交互触发" in response.answer


@pytest.mark.asyncio
async def test_knowledge_chat_service_mentions_frontend_component_mount_chain(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)
    store.initialize()
    route_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-component-chain",
            path="app/api/routes.py",
            file_type="source",
            language="python",
            size_bytes=120,
            is_indexed=True,
        )
    )
    app_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-component-chain",
            path="web/src/App.vue",
            file_type="source",
            language="vue",
            size_bytes=100,
            is_indexed=True,
        )
    )
    child_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-component-chain",
            path="web/src/components/TaskList.vue",
            file_type="source",
            language="vue",
            size_bytes=160,
            is_indexed=True,
        )
    )
    store.insert_chunks(
        [
            KnowledgeChunkRecord(
                task_id="task-chat-component-chain",
                document_id=route_doc,
                chunk_index=0,
                path="app/api/routes.py",
                start_line=1,
                end_line=8,
                symbol_name="list_tasks",
                chunk_kind="function",
                content="@router.get('/tasks')\nasync def list_tasks():\n    return {'items': []}\n",
                summary="app/api/routes.py route list_tasks /tasks",
                token_estimate=20,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-component-chain",
                document_id=app_doc,
                chunk_index=0,
                path="web/src/App.vue",
                start_line=1,
                end_line=6,
                symbol_name="App",
                chunk_kind="component",
                content="<script setup>\nimport TaskList from './components/TaskList.vue'\n</script>\n<template><TaskList /></template>\n",
                summary="web/src/App.vue imports TaskList component",
                token_estimate=18,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-component-chain",
                document_id=child_doc,
                chunk_index=0,
                path="web/src/components/TaskList.vue",
                start_line=1,
                end_line=12,
                symbol_name="loadTasks",
                chunk_kind="function",
                content="<script setup>\nconst loadTasks = async () => fetch('/api/v1/tasks')\n</script>\n<template><button @click=\"loadTasks\">Load</button></template>\n",
                summary="web/src/components/TaskList.vue loadTasks click fetch /api/v1/tasks",
                token_estimate=24,
            ),
        ]
    )
    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-chat-component-chain",
                "file_nodes": [],
                "symbol_nodes": [
                    {
                        "id": "symbol:app/api/routes.py:list_tasks",
                        "file_path": "app/api/routes.py",
                        "name": "list_tasks",
                        "kind": "function",
                        "line": 4,
                        "route_path": "/tasks",
                        "route_method": "GET",
                    },
                    {
                        "id": "symbol:web/src/components/TaskList.vue:loadTasks",
                        "file_path": "web/src/components/TaskList.vue",
                        "name": "loadTasks",
                        "kind": "function",
                        "line": 2,
                    },
                ],
                "edges": [
                    {
                        "type": "maps_to_backend",
                        "source": "symbol:web/src/components/TaskList.vue:loadTasks",
                        "target": "symbol:app/api/routes.py:list_tasks",
                        "path": "/api/v1/tasks",
                        "method": "GET",
                        "frontend_file": "web/src/components/TaskList.vue",
                        "frontend_symbol": "loadTasks",
                        "frontend_trigger": "click",
                        "backend_file": "app/api/routes.py",
                    }
                ],
                "entrypoints": {
                    "backend": {"file_path": "app/main.py", "language": "python", "layer": "backend"},
                    "frontend": {"file_path": "web/src/main.ts", "language": "typescript", "layer": "frontend"},
                },
                "call_chains": [
                    {
                        "summary": "web/src/main.ts -> web/src/App.vue -> web/src/components/TaskList.vue:loadTasks [click] -> GET /api/v1/tasks -> app/api/routes.py:list_tasks",
                        "frontend_file": "web/src/components/TaskList.vue",
                        "frontend_symbol": "loadTasks",
                        "frontend_trigger": "click",
                        "backend_file": "app/api/routes.py",
                        "route_path": "/api/v1/tasks",
                        "method": "GET",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=None)
    response = await service.answer_question(
        task_id="task-chat-component-chain",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="这个请求是从哪个页面和组件一路触发下来的？",
        history=[],
    )

    assert "页面入口 web/src/main.ts" in response.answer
    assert "组件挂载链 web/src/App.vue -> web/src/components/TaskList.vue" in response.answer
    assert "前端入口函数 web/src/components/TaskList.vue:loadTasks" in response.answer


@pytest.mark.asyncio
async def test_knowledge_chat_service_rejects_non_chinese_output_and_downgrades_to_local(tmp_path):
    db_path = _build_knowledge_db(tmp_path)
    repo_map_path = _build_repo_map(tmp_path)

    class EnglishClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            return {
                "answer": "The backend entry is app/main.py",
                "supplemental_notes": [],
                "confidence": "medium",
            }

    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=EnglishClient())
    response = await service.answer_question(
        task_id="task-chat-1",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="后端入口在哪里？",
        history=[],
    )

    assert "app/main.py" in response.answer
    assert response.graph_evidence
    assert response.confidence == "medium"
    assert response.answer_source == "local"


@pytest.mark.asyncio
async def test_knowledge_chat_service_prefers_knowledge_symbols_for_capability_questions(tmp_path):
    db_path = _build_knowledge_db(tmp_path)
    repo_map_path = _build_repo_map(tmp_path)
    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=None)

    response = await service.answer_question(
        task_id="task-chat-1",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="项目里是否存在知识库？",
        history=[],
    )

    assert response.graph_evidence
    assert any(item.kind == "symbol" and item.label == "KnowledgeIndexBuilder" for item in response.graph_evidence)
    assert all(item.kind != "call_chain" for item in response.graph_evidence)
    assert response.answer_source == "local"


@pytest.mark.asyncio
async def test_knowledge_chat_service_uses_graph_paths_to_improve_code_citations(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)
    store.initialize()
    frontend_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-graph",
            path="web/src/services/api.ts",
            file_type="source",
            language="typescript",
            size_bytes=160,
            is_indexed=True,
        )
    )
    backend_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-graph",
            path="app/api/routes/tasks.py",
            file_type="source",
            language="python",
            size_bytes=160,
            is_indexed=True,
        )
    )
    extra_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-graph",
            path="docs/notes.md",
            file_type="doc",
            language="markdown",
            size_bytes=80,
            is_indexed=True,
        )
    )
    store.insert_chunks(
        [
            KnowledgeChunkRecord(
                task_id="task-chat-graph",
                document_id=frontend_doc,
                chunk_index=0,
                path="web/src/services/api.ts",
                start_line=1,
                end_line=12,
                symbol_name="submitTaskQuestion",
                chunk_kind="function",
                content="export async function submitTaskQuestion(taskId: string, question: string) {\n  return requestJson(`/api/v1/tasks/${taskId}/chat`, {\n    method: 'POST',\n  })\n}\n",
                summary="web/src/services/api.ts submitTaskQuestion requestJson /api/v1/tasks/${taskId}/chat",
                token_estimate=32,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-graph",
                document_id=frontend_doc,
                chunk_index=1,
                path="web/src/services/api.ts",
                start_line=1,
                end_line=12,
                symbol_name="submitTaskQuestion",
                chunk_kind="function",
                content="export async function submitTaskQuestion(taskId: string, question: string) {\n  return requestJson(`/api/v1/tasks/${taskId}/chat`, {\n    method: 'POST',\n  })\n}\n",
                summary="duplicate chunk for web/src/services/api.ts submitTaskQuestion",
                token_estimate=32,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-graph",
                document_id=backend_doc,
                chunk_index=0,
                path="app/api/routes/tasks.py",
                start_line=450,
                end_line=520,
                symbol_name="task_chat",
                chunk_kind="function",
                content="@router.post('/tasks/{task_id}/chat')\nasync def task_chat(task_id: str):\n    return {'task_id': task_id}\n",
                summary="app/api/routes/tasks.py task_chat route /tasks/{task_id}/chat",
                token_estimate=24,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-graph",
                document_id=extra_doc,
                chunk_index=0,
                path="docs/notes.md",
                start_line=1,
                end_line=4,
                symbol_name=None,
                chunk_kind="text",
                content="chat route notes and task endpoint summary",
                summary="notes about task chat route",
                token_estimate=12,
            ),
        ]
    )
    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-chat-graph",
                "file_nodes": [],
                "symbol_nodes": [
                    {
                        "id": "symbol:app/api/routes/tasks.py:task_chat",
                        "file_path": "app/api/routes/tasks.py",
                        "name": "task_chat",
                        "kind": "function",
                        "line": 480,
                        "route_path": "/tasks/{task_id}/chat",
                        "route_method": "POST",
                    }
                ],
                "edges": [
                    {
                        "type": "maps_to_backend",
                        "source": "file:web/src/services/api.ts",
                        "target": "symbol:app/api/routes/tasks.py:task_chat",
                        "path": "/api/v1/tasks/{taskId}/chat",
                        "method": "POST",
                        "frontend_file": "web/src/services/api.ts",
                        "backend_file": "app/api/routes/tasks.py",
                    }
                ],
                "entrypoints": {
                    "backend": {"file_path": "app/main.py", "language": "python", "layer": "backend"},
                    "frontend": {"file_path": "web/src/main.ts", "language": "typescript", "layer": "frontend"},
                },
                "call_chains": [
                    {
                        "summary": "web/src/services/api.ts -> POST /api/v1/tasks/{taskId}/chat -> app/api/routes/tasks.py:task_chat",
                        "frontend_file": "web/src/services/api.ts",
                        "backend_file": "app/api/routes/tasks.py",
                        "route_path": "/api/v1/tasks/{taskId}/chat",
                        "method": "POST",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=None)
    response = await service.answer_question(
        task_id="task-chat-graph",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="前端请求如何到后端？",
        history=[],
    )

    citation_paths = [item.path for item in response.citations]
    assert citation_paths[:2] == ["web/src/services/api.ts", "app/api/routes/tasks.py"]
    assert citation_paths.count("web/src/services/api.ts") == 1
    assert "docs/notes.md" not in citation_paths[:2]


@pytest.mark.asyncio
async def test_knowledge_chat_service_rejects_ungrounded_llm_entities_and_falls_back_to_local(tmp_path):
    db_path = _build_knowledge_db(tmp_path)
    repo_map_path = _build_repo_map(tmp_path)

    class HallucinatedClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            return {
                "answer": "这个请求会先进入 LearningOrchestrator，再交给 EventBroker 和 KnowledgeService 处理。",
                "supplemental_notes": ["最终由 RedisRateLimiter 控制执行。"],
                "confidence": "high",
            }

    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=HallucinatedClient())
    response = await service.answer_question(
        task_id="task-chat-1",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="前端请求如何到后端？",
        history=[],
    )

    assert response.answer_source == "local"
    assert "LearningOrchestrator" not in response.answer
    assert "EventBroker" not in "".join(response.supplemental_notes)


@pytest.mark.asyncio
async def test_knowledge_chat_service_call_chain_fallback_includes_frontend_route_and_handler(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)
    store.initialize()
    frontend_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-graph",
            path="web/src/services/api.ts",
            file_type="source",
            language="typescript",
            size_bytes=160,
            is_indexed=True,
        )
    )
    backend_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-graph",
            path="app/api/routes/tasks.py",
            file_type="source",
            language="python",
            size_bytes=160,
            is_indexed=True,
        )
    )
    store.insert_chunks(
        [
            KnowledgeChunkRecord(
                task_id="task-chat-graph",
                document_id=frontend_doc,
                chunk_index=0,
                path="web/src/services/api.ts",
                start_line=1,
                end_line=12,
                symbol_name="submitTaskQuestion",
                chunk_kind="function",
                content="export async function submitTaskQuestion(taskId: string, question: string) {\n  return requestJson(`/api/v1/tasks/${taskId}/chat`, {\n    method: 'POST',\n  })\n}\n",
                summary="web/src/services/api.ts submitTaskQuestion requestJson /api/v1/tasks/${taskId}/chat",
                token_estimate=32,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-graph",
                document_id=backend_doc,
                chunk_index=0,
                path="app/api/routes/tasks.py",
                start_line=450,
                end_line=520,
                symbol_name="task_chat",
                chunk_kind="function",
                content="@router.post('/tasks/{task_id}/chat')\nasync def task_chat(task_id: str):\n    return {'task_id': task_id}\n",
                summary="app/api/routes/tasks.py task_chat route /tasks/{task_id}/chat",
                token_estimate=24,
            ),
        ]
    )
    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-chat-graph",
                "file_nodes": [],
                "symbol_nodes": [
                    {
                        "id": "symbol:app/api/routes/tasks.py:task_chat",
                        "file_path": "app/api/routes/tasks.py",
                        "name": "task_chat",
                        "kind": "function",
                        "line": 480,
                        "route_path": "/tasks/{task_id}/chat",
                        "route_method": "POST",
                    }
                ],
                "edges": [
                    {
                        "type": "maps_to_backend",
                        "source": "file:web/src/services/api.ts",
                        "target": "symbol:app/api/routes/tasks.py:task_chat",
                        "path": "/api/v1/tasks/{taskId}/chat",
                        "method": "POST",
                        "frontend_file": "web/src/services/api.ts",
                        "backend_file": "app/api/routes/tasks.py",
                    }
                ],
                "entrypoints": {
                    "backend": {"file_path": "app/main.py", "language": "python", "layer": "backend"},
                    "frontend": {"file_path": "web/src/main.ts", "language": "typescript", "layer": "frontend"},
                },
                "call_chains": [
                    {
                        "summary": "web/src/services/api.ts -> POST /api/v1/tasks/{taskId}/chat -> app/api/routes/tasks.py:task_chat",
                        "frontend_file": "web/src/services/api.ts",
                        "backend_file": "app/api/routes/tasks.py",
                        "route_path": "/api/v1/tasks/{taskId}/chat",
                        "method": "POST",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=None)
    response = await service.answer_question(
        task_id="task-chat-graph",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="前端请求如何到后端？",
        history=[],
    )

    assert "前端文件 web/src/services/api.ts" in response.answer
    assert "接口路由 POST /api/v1/tasks/{taskId}/chat" in response.answer
    assert "后端处理位置 app/api/routes/tasks.py:task_chat" in response.answer


@pytest.mark.asyncio
async def test_knowledge_chat_service_multi_hop_call_chain_mentions_backend_followup(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)
    store.initialize()
    frontend_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-multi-hop",
            path="web/src/services/api.ts",
            file_type="source",
            language="typescript",
            size_bytes=160,
            is_indexed=True,
        )
    )
    route_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-multi-hop",
            path="app/api/routes/tasks.py",
            file_type="source",
            language="python",
            size_bytes=180,
            is_indexed=True,
        )
    )
    service_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-multi-hop",
            path="app/services/reporting.py",
            file_type="source",
            language="python",
            size_bytes=120,
            is_indexed=True,
        )
    )
    store.insert_chunks(
        [
            KnowledgeChunkRecord(
                task_id="task-chat-multi-hop",
                document_id=frontend_doc,
                chunk_index=0,
                path="web/src/services/api.ts",
                start_line=1,
                end_line=12,
                symbol_name="submitTaskQuestion",
                chunk_kind="function",
                content="export async function submitTaskQuestion(taskId: string, question: string) {\n  return requestJson(`/api/v1/tasks/${taskId}/chat`, {\n    method: 'POST',\n  })\n}\n",
                summary="web/src/services/api.ts submitTaskQuestion requestJson /api/v1/tasks/${taskId}/chat",
                token_estimate=32,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-multi-hop",
                document_id=route_doc,
                chunk_index=0,
                path="app/api/routes/tasks.py",
                start_line=450,
                end_line=520,
                symbol_name="task_chat",
                chunk_kind="function",
                content="@router.post('/tasks/{task_id}/chat')\nasync def task_chat(task_id: str):\n    return generate_report(task_id)\n",
                summary="app/api/routes/tasks.py task_chat route /tasks/{task_id}/chat generate_report",
                token_estimate=24,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-multi-hop",
                document_id=service_doc,
                chunk_index=0,
                path="app/services/reporting.py",
                start_line=1,
                end_line=8,
                symbol_name="generate_report",
                chunk_kind="function",
                content="def generate_report(task_id: str):\n    return {'task_id': task_id}\n",
                summary="app/services/reporting.py generate_report task report",
                token_estimate=16,
            ),
        ]
    )
    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-chat-multi-hop",
                "file_nodes": [],
                "symbol_nodes": [
                    {
                        "id": "symbol:app/api/routes/tasks.py:task_chat",
                        "file_path": "app/api/routes/tasks.py",
                        "name": "task_chat",
                        "kind": "function",
                        "line": 480,
                        "route_path": "/tasks/{task_id}/chat",
                        "route_method": "POST",
                    },
                    {
                        "id": "symbol:app/services/reporting.py:generate_report",
                        "file_path": "app/services/reporting.py",
                        "name": "generate_report",
                        "kind": "function",
                        "line": 1,
                    },
                ],
                "edges": [
                    {
                        "type": "maps_to_backend",
                        "source": "file:web/src/services/api.ts",
                        "target": "symbol:app/api/routes/tasks.py:task_chat",
                        "path": "/api/v1/tasks/{taskId}/chat",
                        "method": "POST",
                        "frontend_file": "web/src/services/api.ts",
                        "backend_file": "app/api/routes/tasks.py",
                    },
                    {
                        "type": "calls",
                        "source": "symbol:app/api/routes/tasks.py:task_chat",
                        "target": "symbol:app/services/reporting.py:generate_report",
                        "file_path": "app/api/routes/tasks.py",
                    },
                ],
                "entrypoints": {
                    "backend": {"file_path": "app/main.py", "language": "python", "layer": "backend"},
                    "frontend": {"file_path": "web/src/main.ts", "language": "typescript", "layer": "frontend"},
                },
                "call_chains": [
                    {
                        "summary": "web/src/services/api.ts -> POST /api/v1/tasks/{taskId}/chat -> app/api/routes/tasks.py:task_chat -> app/services/reporting.py:generate_report",
                        "frontend_file": "web/src/services/api.ts",
                        "backend_file": "app/api/routes/tasks.py",
                        "route_path": "/api/v1/tasks/{taskId}/chat",
                        "method": "POST",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    service = KnowledgeChatService(retriever=KnowledgeRetriever(), client=None)
    response = await service.answer_question(
        task_id="task-chat-multi-hop",
        db_path=db_path,
        repo_map_path=repo_map_path,
        question="前端请求如何到后端，后端接着又调用了什么？",
        history=[],
    )

    assert "后续还会调用 app/services/reporting.py:generate_report" in response.answer


def _build_repo_map(tmp_path):
    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-chat-1",
                "file_nodes": [
                    {"id": "file:app/main.py", "file_path": "app/main.py", "language": "python", "layer": "backend"},
                    {"id": "file:web/App.vue", "file_path": "web/App.vue", "language": "vue", "layer": "frontend"},
                ],
                "symbol_nodes": [
                    {
                        "id": "symbol:app/main.py:health",
                        "file_path": "app/main.py",
                        "name": "health",
                        "kind": "function",
                        "line": 4,
                        "route_path": "/health",
                        "route_method": "GET",
                    },
                    {
                        "id": "symbol:app/services/knowledge/index_builder.py:KnowledgeIndexBuilder",
                        "file_path": "app/services/knowledge/index_builder.py",
                        "name": "KnowledgeIndexBuilder",
                        "kind": "class",
                        "line": 12,
                    },
                ],
                "edges": [
                    {
                        "type": "maps_to_backend",
                        "source": "file:web/App.vue",
                        "target": "symbol:app/main.py:health",
                        "path": "/health",
                        "method": "GET",
                        "frontend_file": "web/App.vue",
                        "backend_file": "app/main.py",
                    }
                ],
                "entrypoints": {
                    "backend": {"file_path": "app/main.py", "language": "python", "layer": "backend"},
                    "frontend": {"file_path": "web/App.vue", "language": "vue", "layer": "frontend"},
                },
                "call_chains": [
                    {
                        "summary": "web/App.vue -> GET /health -> app/main.py:health",
                        "frontend_file": "web/App.vue",
                        "backend_file": "app/main.py",
                        "route_path": "/health",
                        "method": "GET",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return repo_map_path


def _build_knowledge_db(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)
    store.initialize()
    app_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-1",
            path="app/main.py",
            file_type="source",
            language="python",
            size_bytes=120,
            is_indexed=True,
        )
    )
    web_doc = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-chat-1",
            path="web/App.vue",
            file_type="source",
            language="vue",
            size_bytes=120,
            is_indexed=True,
        )
    )
    store.insert_chunks(
        [
            KnowledgeChunkRecord(
                task_id="task-chat-1",
                document_id=app_doc,
                chunk_index=0,
                path="app/main.py",
                start_line=1,
                end_line=8,
                symbol_name="health",
                chunk_kind="function",
                content="from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\nasync def health():\n    return {'ok': True}\n",
                summary="app/main.py backend entry FastAPI health",
                token_estimate=24,
            ),
            KnowledgeChunkRecord(
                task_id="task-chat-1",
                document_id=web_doc,
                chunk_index=0,
                path="web/App.vue",
                start_line=1,
                end_line=10,
                symbol_name="App",
                chunk_kind="component",
                content="<script setup>\nconst loadHealth = async () => fetch('/health')\n</script>\n",
                summary="web/App.vue frontend component fetch health",
                token_estimate=18,
            ),
        ]
    )
    return db_path
