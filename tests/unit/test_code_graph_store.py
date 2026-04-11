from __future__ import annotations

from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode
from app.services.code_graph.storage import CodeGraphStore


def test_code_graph_store_persists_files_symbols_edges_and_summaries(tmp_path):
    db_path = tmp_path / "knowledge.db"
    graph_store = CodeGraphStore(db_path)
    graph_store.initialize()

    graph_store.upsert_files(
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
    graph_store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/main.py:health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=1,
                end_line=4,
                summary_zh="",
                language="python",
            )
        ]
    )
    graph_store.insert_edges(
        [
            CodeEdge(
                task_id="task-1",
                from_symbol_id="function:python:app/main.py:health",
                to_symbol_id="function:python:app/main.py:health",
                edge_kind="contains",
                source_path="app/main.py",
                line=1,
            )
        ]
    )
    graph_store.update_file_summary(
        task_id="task-1",
        path="app/main.py",
        summary_zh="该文件负责定义 FastAPI 应用入口。",
    )
    graph_store.update_symbol_summary(
        task_id="task-1",
        symbol_id="function:python:app/main.py:health",
        summary_zh="该函数负责暴露健康检查接口。",
    )

    files = graph_store.list_files(task_id="task-1")
    symbols = graph_store.list_symbols(task_id="task-1")
    edges = graph_store.list_out_edges(
        task_id="task-1",
        symbol_id="function:python:app/main.py:health",
    )

    assert files[0].summary_zh == "该文件负责定义 FastAPI 应用入口。"
    assert files[0].entry_role == "backend_entry"
    assert symbols[0].summary_zh == "该函数负责暴露健康检查接口。"
    assert symbols[0].qualified_name == "app.main.health"
    assert edges[0].edge_kind == "contains"


def test_code_graph_store_searches_fts_and_registers_embeddings(tmp_path):
    db_path = tmp_path / "knowledge.db"
    graph_store = CodeGraphStore(db_path)
    graph_store.initialize()

    graph_store.upsert_files(
        [
            CodeFileNode(
                task_id="task-1",
                path="app/main.py",
                language="python",
                file_kind="source",
                summary_zh="该文件负责定义 FastAPI 应用入口和健康检查接口。",
                entry_role="backend_entry",
            )
        ]
    )
    graph_store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/main.py:health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=1,
                end_line=4,
                summary_zh="该函数负责提供 FastAPI 健康检查能力。",
                language="python",
            )
        ]
    )

    graph_store.register_embedding(
        task_id="task-1",
        item_type="symbol",
        item_ref_id="function:python:app/main.py:health",
        vector_store="qdrant",
        collection_name="repo_semantic_items",
        vector_point_id="point-1",
        embedding_model="test-embed",
        content_hash="abc123",
        status="ready",
    )

    symbol_hits = graph_store.search_symbols_fts(
        task_id="task-1",
        query="FastAPI health",
        limit=5,
    )
    file_hits = graph_store.search_files_fts(
        task_id="task-1",
        query="FastAPI main",
        limit=5,
    )
    registry_rows = graph_store.list_embedding_registry(task_id="task-1")

    assert symbol_hits[0].qualified_name == "app.main.health"
    assert symbol_hits[0].source == "exact"
    assert file_hits[0].path == "app/main.py"
    assert registry_rows[0]["vector_store"] == "qdrant"
    assert registry_rows[0]["vector_point_id"] == "point-1"


def test_code_graph_store_has_graph_index_returns_false_without_schema(tmp_path):
    db_path = tmp_path / "knowledge.db"
    db_path.touch()

    graph_store = CodeGraphStore(db_path)

    assert graph_store.has_graph_index(task_id="task-1") is False


def test_code_graph_store_has_graph_index_returns_true_with_task_data(tmp_path):
    db_path = tmp_path / "knowledge.db"
    graph_store = CodeGraphStore(db_path)
    graph_store.initialize()
    graph_store.upsert_files(
        [
            CodeFileNode(
                task_id="task-1",
                path="app/main.py",
                language="python",
                file_kind="source",
                summary_zh="backend entry",
                entry_role="backend_entry",
            )
        ]
    )

    assert graph_store.has_graph_index(task_id="task-1") is True
    assert graph_store.has_graph_index(task_id="task-2") is False
