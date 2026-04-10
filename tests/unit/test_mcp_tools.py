from __future__ import annotations

import json

import pytest

from app.core.models import TaskChatMessage
from app.services.chat.mcp_tools import RepositoryQaToolSession
from app.storage.knowledge_store import KnowledgeChunkRecord, KnowledgeDocumentRecord, SQLiteKnowledgeStore


class _FakeTaskStore:
    def __init__(self, messages: list[TaskChatMessage]) -> None:
        self._messages = messages

    async def get_chat_messages(self, task_id: str) -> list[TaskChatMessage]:
        assert task_id == "task-mcp-tools"
        return self._messages


@pytest.mark.asyncio
async def test_repository_qa_tool_session_core_tools(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "app").mkdir(parents=True)
    (repo_root / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n\n"
        "@app.get('/health')\n"
        "async def health() -> dict[str, bool]:\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )
    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-mcp-tools",
                "entrypoints": {
                    "backend": {"file_path": "app/main.py", "language": "python", "layer": "backend"},
                    "frontend": {"file_path": "web/src/main.ts", "language": "typescript", "layer": "frontend"},
                },
                "symbol_nodes": [
                    {
                        "id": "symbol:app/main.py:health",
                        "file_path": "app/main.py",
                        "name": "health",
                        "kind": "function",
                        "line": 5,
                    }
                ],
                "edges": [
                    {
                        "type": "maps_to_backend",
                        "source": "file:web/src/App.vue",
                        "target": "symbol:app/main.py:health",
                        "path": "/health",
                        "method": "GET",
                        "frontend_file": "web/src/App.vue",
                        "backend_file": "app/main.py",
                    }
                ],
                "call_chains": [
                    {
                        "summary": "web/src/App.vue -> GET /health -> app/main.py:health",
                        "frontend_file": "web/src/App.vue",
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
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)
    store.initialize()
    document_id = store.upsert_document(
        KnowledgeDocumentRecord(
            task_id="task-mcp-tools",
            path="app/main.py",
            file_type="source",
            language="python",
            size_bytes=120,
            is_indexed=True,
        )
    )
    store.insert_chunks(
        [
            KnowledgeChunkRecord(
                task_id="task-mcp-tools",
                document_id=document_id,
                chunk_index=0,
                path="app/main.py",
                start_line=1,
                end_line=6,
                symbol_name="health",
                chunk_kind="function",
                content="from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\nasync def health():\n    return {'ok': True}\n",
                summary="backend route health",
                token_estimate=24,
            )
        ]
    )
    task_store = _FakeTaskStore(
        messages=[
            TaskChatMessage(message_id="u-1", role="user", content="先看后端入口"),
            TaskChatMessage(message_id="a-1", role="assistant", content="入口在 app/main.py"),
            TaskChatMessage(message_id="u-2", role="user", content="再看 health 路由"),
        ]
    )

    session = RepositoryQaToolSession(
        task_id="task-mcp-tools",
        repo_root=repo_root,
        repo_map_path=repo_map_path,
        knowledge_db_path=db_path,
        task_store=task_store,
    )

    tools = await session.list_tools()
    tool_names = {item["name"] for item in tools}
    search_result = await session.call_tool("search_code", {"query": "health", "limit": 3})
    repo_map_result = await session.call_tool("load_repo_map", {})
    trace_by_query_result = await session.call_tool("trace_call_chain", {"query": "/health"})
    trace_by_entry_result = await session.call_tool("trace_call_chain", {"entry": "backend"})
    open_file_result = await session.call_tool("open_file", {"path": "app/main.py", "start_line": 1, "end_line": 4})
    open_symbol_result = await session.call_tool("open_file", {"symbol": "health"})
    history_result = await session.call_tool("read_history", {"limit": 2})

    assert {"search_code", "load_repo_map", "trace_call_chain", "open_file", "read_history"} <= tool_names
    for tool in tools:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"

    assert search_result["success"] is True
    assert search_result["payload"]["hits"]
    assert search_result["payload"]["hits"][0]["path"] == "app/main.py"

    assert repo_map_result["success"] is True
    assert "entrypoints" in repo_map_result["payload"]
    assert repo_map_result["payload"]["call_chains"][0]["route_path"] == "/health"

    assert trace_by_query_result["success"] is True
    assert trace_by_query_result["payload"]["chains"]
    assert "/health" in trace_by_query_result["payload"]["chains"][0]["summary"]

    assert trace_by_entry_result["success"] is True
    assert trace_by_entry_result["payload"]["chains"]

    assert open_file_result["success"] is True
    assert open_file_result["payload"]["path"] == "app/main.py"
    assert open_file_result["payload"]["start_line"] == 1
    assert "FastAPI" in open_file_result["payload"]["snippet"]

    assert open_symbol_result["success"] is True
    assert open_symbol_result["payload"]["symbol"] == "health"
    assert open_symbol_result["payload"]["path"] == "app/main.py"

    assert history_result["success"] is True
    assert len(history_result["payload"]["messages"]) == 2
    assert "assistant" in history_result["summary"]


@pytest.mark.asyncio
async def test_repository_qa_tool_session_returns_structured_failures_for_missing_context(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    session = RepositoryQaToolSession(
        task_id="task-mcp-tools",
        repo_root=repo_root,
        repo_map_path=tmp_path / "missing-repo-map.json",
        knowledge_db_path=tmp_path / "missing-knowledge.db",
        task_store=None,
    )

    unknown_result = await session.call_tool("unknown_tool", {})
    search_result = await session.call_tool("search_code", {})
    repo_map_result = await session.call_tool("load_repo_map", {})
    trace_result = await session.call_tool("trace_call_chain", {})
    open_result = await session.call_tool("open_file", {})
    history_result = await session.call_tool("read_history", {})

    assert unknown_result["success"] is False
    assert "unknown" in unknown_result["summary"].lower()

    assert search_result["success"] is False
    assert "query" in search_result["summary"].lower()

    assert repo_map_result["success"] is False
    assert "repo map" in repo_map_result["summary"].lower()

    assert trace_result["success"] is False
    assert "query" in trace_result["summary"].lower()

    assert open_result["success"] is False
    assert "path" in open_result["summary"].lower()

    assert history_result["success"] is False
    assert "history" in history_result["summary"].lower()


@pytest.mark.asyncio
async def test_repository_qa_tool_session_limits_large_payloads(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "app").mkdir(parents=True)
    large_file = repo_root / "app" / "large.py"
    large_file.write_text("x" * 50_000, encoding="utf-8")

    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-mcp-tools",
                "entrypoints": {
                    "backend": {"file_path": "app/large.py", "language": "python", "layer": "backend"},
                },
                "symbol_nodes": [
                    {"id": f"symbol:app/large.py:item_{index}", "file_path": "app/large.py", "name": f"item_{index}"}
                    for index in range(1, 21)
                ],
                "edges": [
                    {"type": "calls", "source": f"symbol:{index}", "target": f"symbol:{index + 1}"}
                    for index in range(1, 21)
                ],
                "call_chains": [
                    {"summary": f"chain-{index}", "backend_file": "app/large.py", "route_path": f"/route-{index}"}
                    for index in range(1, 21)
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    session = RepositoryQaToolSession(
        task_id="task-mcp-tools",
        repo_root=repo_root,
        repo_map_path=repo_map_path,
        knowledge_db_path=tmp_path / "missing.db",
        task_store=None,
    )

    repo_map_result = await session.call_tool("load_repo_map", {})
    open_result = await session.call_tool("open_file", {"path": "app/large.py"})

    assert repo_map_result["success"] is True
    assert len(repo_map_result["payload"]["symbol_nodes"]) <= 10
    assert len(repo_map_result["payload"]["edges"]) <= 10
    assert len(repo_map_result["payload"]["call_chains"]) <= 5

    assert open_result["success"] is True
    assert open_result["payload"]["end_line"] <= 80
    assert len(open_result["payload"]["snippet"]) <= 4000


@pytest.mark.asyncio
async def test_repository_qa_tool_session_rejects_stale_symbol_locations(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "app").mkdir(parents=True)
    (repo_root / "app" / "main.py").write_text("line1\nline2\nline3\n", encoding="utf-8")

    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-mcp-tools",
                "symbol_nodes": [
                    {
                        "id": "symbol:app/main.py:health",
                        "file_path": "app/main.py",
                        "name": "health",
                        "kind": "function",
                        "line": 50,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    session = RepositoryQaToolSession(
        task_id="task-mcp-tools",
        repo_root=repo_root,
        repo_map_path=repo_map_path,
        knowledge_db_path=tmp_path / "missing.db",
        task_store=None,
    )

    result = await session.call_tool("open_file", {"symbol": "health"})

    assert result["success"] is False
    assert "resolve" in result["summary"].lower() or "stale" in result["summary"].lower()
