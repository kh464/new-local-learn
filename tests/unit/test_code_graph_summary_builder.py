from __future__ import annotations

from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode
from app.services.code_graph.summary_builder import CodeSummaryBuilder


def test_code_summary_builder_generates_chinese_file_and_symbol_summaries():
    builder = CodeSummaryBuilder()
    file_node = CodeFileNode(
        task_id="task-1",
        path="app/api/routes.py",
        language="python",
        file_kind="source",
        entry_role=None,
    )
    route_symbol = CodeSymbolNode(
        task_id="task-1",
        symbol_id="route:python:app/api/routes.py:app.api.routes.__route__.router.get:/tasks",
        symbol_kind="route",
        name="GET /tasks",
        qualified_name="app.api.routes.__route__.router.get:/tasks",
        file_path="app/api/routes.py",
        start_line=10,
        end_line=10,
        language="python",
    )
    handler_symbol = CodeSymbolNode(
        task_id="task-1",
        symbol_id="function:python:app/api/routes.py:app.api.routes.list_tasks",
        symbol_kind="function",
        name="list_tasks",
        qualified_name="app.api.routes.list_tasks",
        file_path="app/api/routes.py",
        start_line=11,
        end_line=13,
        language="python",
    )
    call_edge = CodeEdge(
        task_id="task-1",
        from_symbol_id=handler_symbol.symbol_id,
        to_symbol_id="function:python:app/services/reporting.py:app.services.reporting.generate_report",
        edge_kind="calls",
        source_path="app/api/routes.py",
        line=12,
    )

    file_summary = builder.build_file_summary(file_node=file_node, symbols=[route_symbol, handler_symbol])
    route_summary = builder.build_symbol_summary(symbol=route_symbol, outgoing_edges=[])
    handler_summary = builder.build_symbol_summary(symbol=handler_symbol, outgoing_edges=[call_edge])

    assert "中文" not in file_summary
    assert "routes.py" in file_summary
    assert "路由" in file_summary
    assert "GET /tasks" in route_summary
    assert "list_tasks" in handler_summary
    assert "调用" in handler_summary
