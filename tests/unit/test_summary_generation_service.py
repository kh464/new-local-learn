from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.code_graph.models import CodeFileNode, CodeSymbolNode
from app.services.code_graph.storage import CodeGraphStore
from app.services.code_graph.summary_generation_service import SummaryGenerationService


@pytest.mark.asyncio
async def test_summary_generation_service_updates_file_and_symbol_records(tmp_path):
    db_path = tmp_path / "knowledge.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "app").mkdir()
    (repo_root / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/health')\ndef health():\n    return {'status': 'ok'}\n",
        encoding="utf-8",
    )

    store = CodeGraphStore(db_path)
    store.initialize()
    store.upsert_files(
        [
            CodeFileNode(
                task_id="task-1",
                path="app/main.py",
                language="python",
                file_kind="source",
                summary_zh="",
                entry_role="backend_entry",
            )
        ]
    )
    store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/main.py:app.main.health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=5,
                end_line=6,
                summary_zh="",
                language="python",
            )
        ]
    )

    class StubLlmSummaryService:
        async def generate_file_summary(self, **kwargs):
            return SimpleNamespace(
                summary_zh="该文件负责提供 FastAPI 应用入口。",
                responsibility_zh="负责初始化应用并挂载路由",
                upstream_zh="由 Uvicorn 导入启动",
                downstream_zh="向 health 处理函数分发请求",
                keywords_zh=["FastAPI", "入口"],
                summary_confidence="high",
            )

        async def generate_symbol_summary(self, **kwargs):
            return SimpleNamespace(
                summary_zh="该函数负责返回健康检查结果。",
                input_output_zh="无输入，输出健康状态字典",
                side_effects_zh="无外部副作用",
                call_targets_zh="无下游调用",
                callers_zh="由 FastAPI 路由触发",
                summary_confidence="high",
            )

    service = SummaryGenerationService(
        graph_store=store,
        llm_summary_service=StubLlmSummaryService(),
    )
    await service.build(task_id="task-1", db_path=db_path, repo_root=repo_root)

    files = store.list_files(task_id="task-1")
    symbols = store.list_symbols(task_id="task-1")

    assert files[0].summary_source == "llm"
    assert files[0].responsibility_zh == "负责初始化应用并挂载路由"
    assert files[0].summary_confidence == "high"
    assert symbols[0].input_output_zh == "无输入，输出健康状态字典"
    assert symbols[0].summary_source == "llm"


@pytest.mark.asyncio
async def test_summary_generation_service_falls_back_to_rule_summary_when_llm_missing(tmp_path):
    db_path = tmp_path / "knowledge.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "pkg").mkdir()
    (repo_root / "pkg" / "worker.py").write_text(
        "def run_job(task_id: str) -> dict[str, str]:\n    return {'task_id': task_id}\n",
        encoding="utf-8",
    )

    store = CodeGraphStore(db_path)
    store.initialize()
    store.upsert_files(
        [
            CodeFileNode(
                task_id="task-2",
                path="pkg/worker.py",
                language="python",
                file_kind="source",
                summary_zh="",
            )
        ]
    )
    store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-2",
                symbol_id="function:python:pkg/worker.py:pkg.worker.run_job",
                symbol_kind="function",
                name="run_job",
                qualified_name="pkg.worker.run_job",
                file_path="pkg/worker.py",
                start_line=1,
                end_line=2,
                summary_zh="",
                language="python",
                signature="def run_job(task_id: str) -> dict[str, str]",
            )
        ]
    )

    service = SummaryGenerationService(graph_store=store, llm_summary_service=None)
    await service.build(task_id="task-2", db_path=db_path, repo_root=repo_root)

    files = store.list_files(task_id="task-2")
    symbols = store.list_symbols(task_id="task-2")

    assert files[0].summary_source == "rule"
    assert files[0].summary_zh
    assert symbols[0].summary_source == "rule"
    assert symbols[0].summary_zh


@pytest.mark.asyncio
async def test_summary_generation_service_limits_llm_calls_and_falls_back_for_remaining_records(tmp_path):
    db_path = tmp_path / "knowledge.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "app").mkdir()
    (repo_root / "app" / "main.py").write_text(
        "def create_app():\n    return None\n",
        encoding="utf-8",
    )
    (repo_root / "app" / "worker.py").write_text(
        "def run_job():\n    return None\n",
        encoding="utf-8",
    )

    store = CodeGraphStore(db_path)
    store.initialize()
    store.upsert_files(
        [
            CodeFileNode(
                task_id="task-3",
                path="app/main.py",
                language="python",
                file_kind="source",
                summary_zh="",
                entry_role="backend_entry",
            ),
            CodeFileNode(
                task_id="task-3",
                path="app/worker.py",
                language="python",
                file_kind="source",
                summary_zh="",
            ),
        ]
    )
    store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-3",
                symbol_id="route:python:app/main.py:app.main.create_app.__route__.app.get:/health",
                symbol_kind="route",
                name="GET /health",
                qualified_name="app.main.create_app.__route__.app.get:/health",
                file_path="app/main.py",
                start_line=1,
                end_line=1,
                summary_zh="",
                language="python",
            ),
            CodeSymbolNode(
                task_id="task-3",
                symbol_id="function:python:app/main.py:app.main.create_app.health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.create_app.health",
                file_path="app/main.py",
                start_line=1,
                end_line=2,
                summary_zh="",
                language="python",
            ),
            CodeSymbolNode(
                task_id="task-3",
                symbol_id="class:python:app/worker.py:app.worker.JobRunner",
                symbol_kind="class",
                name="JobRunner",
                qualified_name="app.worker.JobRunner",
                file_path="app/worker.py",
                start_line=1,
                end_line=2,
                summary_zh="",
                language="python",
            ),
            CodeSymbolNode(
                task_id="task-3",
                symbol_id="function:python:app/worker.py:app.worker.run_job",
                symbol_kind="function",
                name="run_job",
                qualified_name="app.worker.run_job",
                file_path="app/worker.py",
                start_line=1,
                end_line=2,
                summary_zh="",
                language="python",
            ),
        ]
    )

    calls = {"file": 0, "symbol": 0}

    class StubLlmSummaryService:
        async def generate_file_summary(self, **kwargs):
            calls["file"] += 1
            return SimpleNamespace(
                summary_zh="文件 LLM 摘要",
                responsibility_zh="LLM",
                upstream_zh="",
                downstream_zh="",
                keywords_zh=["LLM"],
                summary_confidence="high",
            )

        async def generate_symbol_summary(self, **kwargs):
            calls["symbol"] += 1
            return SimpleNamespace(
                summary_zh="符号 LLM 摘要",
                input_output_zh="LLM",
                side_effects_zh="",
                call_targets_zh="",
                callers_zh="",
                summary_confidence="high",
            )

    service = SummaryGenerationService(
        graph_store=store,
        llm_summary_service=StubLlmSummaryService(),
        max_llm_file_summaries=1,
        max_llm_symbol_summaries=2,
    )
    await service.build(task_id="task-3", db_path=db_path, repo_root=repo_root)

    files = store.list_files(task_id="task-3")
    symbols = store.list_symbols(task_id="task-3")

    assert calls == {"file": 1, "symbol": 2}
    assert sum(1 for item in files if item.summary_source == "llm") == 1
    assert sum(1 for item in files if item.summary_source == "rule") == 1
    assert sum(1 for item in symbols if item.summary_source == "llm") == 2
    assert sum(1 for item in symbols if item.summary_source == "rule") == 2


@pytest.mark.asyncio
async def test_summary_generation_service_runs_llm_requests_with_parallelism(tmp_path):
    db_path = tmp_path / "knowledge.db"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "app").mkdir()
    (repo_root / "app" / "main.py").write_text("def a():\n    return 1\n", encoding="utf-8")
    (repo_root / "app" / "worker.py").write_text("def b():\n    return 2\n", encoding="utf-8")

    store = CodeGraphStore(db_path)
    store.initialize()
    store.upsert_files(
        [
            CodeFileNode(task_id="task-4", path="app/main.py", language="python", file_kind="source", summary_zh="", entry_role="backend_entry"),
            CodeFileNode(task_id="task-4", path="app/worker.py", language="python", file_kind="source", summary_zh=""),
        ]
    )
    store.upsert_symbols(
        [
            CodeSymbolNode(task_id="task-4", symbol_id="function:python:app/main.py:app.main.a", symbol_kind="function", name="a", qualified_name="app.main.a", file_path="app/main.py", start_line=1, end_line=2, summary_zh="", language="python"),
            CodeSymbolNode(task_id="task-4", symbol_id="function:python:app/worker.py:app.worker.b", symbol_kind="function", name="b", qualified_name="app.worker.b", file_path="app/worker.py", start_line=1, end_line=2, summary_zh="", language="python"),
        ]
    )

    counters = {"current": 0, "max": 0}

    class StubLlmSummaryService:
        async def generate_file_summary(self, **kwargs):
            counters["current"] += 1
            counters["max"] = max(counters["max"], counters["current"])
            await asyncio.sleep(0.01)
            counters["current"] -= 1
            return SimpleNamespace(
                summary_zh="文件 LLM 摘要",
                responsibility_zh="LLM",
                upstream_zh="",
                downstream_zh="",
                keywords_zh=["LLM"],
                summary_confidence="high",
            )

        async def generate_symbol_summary(self, **kwargs):
            counters["current"] += 1
            counters["max"] = max(counters["max"], counters["current"])
            await asyncio.sleep(0.01)
            counters["current"] -= 1
            return SimpleNamespace(
                summary_zh="符号 LLM 摘要",
                input_output_zh="LLM",
                side_effects_zh="",
                call_targets_zh="",
                callers_zh="",
                summary_confidence="high",
            )

    service = SummaryGenerationService(
        graph_store=store,
        llm_summary_service=StubLlmSummaryService(),
        max_llm_file_summaries=2,
        max_llm_symbol_summaries=2,
        max_llm_parallelism=4,
    )
    await service.build(task_id="task-4", db_path=db_path, repo_root=repo_root)

    assert counters["max"] > 1
