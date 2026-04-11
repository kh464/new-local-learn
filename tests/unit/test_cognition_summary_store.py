from __future__ import annotations

from app.services.code_graph.models import CodeFileNode, CodeSymbolNode
from app.services.code_graph.storage import CodeGraphStore


def test_code_graph_store_persists_structured_file_summary_fields(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = CodeGraphStore(db_path)
    store.initialize()

    store.upsert_files(
        [
            CodeFileNode(
                task_id="task-1",
                path="app/main.py",
                language="python",
                file_kind="source",
                summary_zh="该文件负责应用入口。",
                entry_role="backend_entry",
                responsibility_zh="负责创建 FastAPI 应用并注册基础路由",
                upstream_zh="由 Uvicorn 启动时导入",
                downstream_zh="将请求分发到 health 路由",
                keywords_zh=["FastAPI", "入口", "health"],
                summary_source="llm",
                summary_version=1,
                summary_confidence="high",
            )
        ]
    )

    files = store.list_files(task_id="task-1")

    assert files[0].responsibility_zh == "负责创建 FastAPI 应用并注册基础路由"
    assert files[0].upstream_zh == "由 Uvicorn 启动时导入"
    assert files[0].downstream_zh == "将请求分发到 health 路由"
    assert files[0].keywords_zh == ["FastAPI", "入口", "health"]
    assert files[0].summary_source == "llm"
    assert files[0].summary_version == 1
    assert files[0].summary_confidence == "high"


def test_code_graph_store_persists_structured_symbol_summary_fields(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = CodeGraphStore(db_path)
    store.initialize()

    store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/main.py:app.main.health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=4,
                end_line=5,
                summary_zh="该函数负责健康检查。",
                language="python",
                input_output_zh="无输入，输出健康状态字典",
                side_effects_zh="无外部副作用",
                call_targets_zh="无下游调用",
                callers_zh="由 FastAPI 路由调用",
                summary_source="llm",
                summary_version=1,
                summary_confidence="medium",
            )
        ]
    )

    symbols = store.list_symbols(task_id="task-1")

    assert symbols[0].input_output_zh == "无输入，输出健康状态字典"
    assert symbols[0].side_effects_zh == "无外部副作用"
    assert symbols[0].call_targets_zh == "无下游调用"
    assert symbols[0].callers_zh == "由 FastAPI 路由调用"
    assert symbols[0].summary_source == "llm"
    assert symbols[0].summary_version == 1
    assert symbols[0].summary_confidence == "medium"
