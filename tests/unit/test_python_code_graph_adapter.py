from __future__ import annotations

from pathlib import Path

from app.services.code_graph.adapters.python import PythonCodeGraphAdapter


def test_python_code_graph_adapter_extracts_symbols_edges_and_routes(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "app" / "api").mkdir(parents=True)
    file_path = repo_root / "app" / "api" / "routes.py"
    file_path.write_text(
        "from fastapi import APIRouter\n"
        "from app.services.reporting import generate_report\n\n"
        "router = APIRouter()\n\n"
        "def helper():\n"
        "    return generate_report()\n\n"
        "@router.get('/tasks')\n"
        "async def list_tasks():\n"
        "    return helper()\n\n"
        "class TaskService:\n"
        "    def build(self):\n"
        "        return helper()\n",
        encoding="utf-8",
    )

    result = PythonCodeGraphAdapter().extract_file(
        task_id="task-1",
        repo_root=repo_root,
        file_path=file_path,
    )

    assert len(result.files) == 1
    assert result.files[0].path == "app/api/routes.py"
    assert result.files[0].language == "python"

    symbols_by_name = {symbol.qualified_name: symbol for symbol in result.symbols}
    assert "app.api.routes.helper" in symbols_by_name
    assert "app.api.routes.list_tasks" in symbols_by_name
    assert "app.api.routes.TaskService" in symbols_by_name
    assert "app.api.routes.TaskService.build" in symbols_by_name
    assert any(symbol.symbol_kind == "route" and symbol.name == "GET /tasks" for symbol in result.symbols)

    edge_pairs = {(edge.edge_kind, edge.from_symbol_id, edge.to_symbol_id) for edge in result.edges}
    helper_id = symbols_by_name["app.api.routes.helper"].symbol_id
    list_tasks_id = symbols_by_name["app.api.routes.list_tasks"].symbol_id
    class_id = symbols_by_name["app.api.routes.TaskService"].symbol_id
    build_id = symbols_by_name["app.api.routes.TaskService.build"].symbol_id
    route_id = next(symbol.symbol_id for symbol in result.symbols if symbol.symbol_kind == "route")

    assert ("contains", class_id, build_id) in edge_pairs
    assert any(kind == "contains" and to_id == helper_id for kind, _, to_id in edge_pairs)
    assert ("calls", list_tasks_id, helper_id) in edge_pairs
    assert ("calls", build_id, helper_id) in edge_pairs
    assert ("routes_to", route_id, list_tasks_id) in edge_pairs
    assert any(edge.edge_kind == "imports" for edge in result.edges)
    assert any(call.callee_name == "generate_report" for call in result.unresolved_calls)


def test_python_code_graph_adapter_extracts_nested_route_handlers_inside_factory_function(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "app").mkdir(parents=True)
    file_path = repo_root / "app" / "main.py"
    file_path.write_text(
        "from fastapi import FastAPI\n\n"
        "def create_app():\n"
        "    app = FastAPI()\n\n"
        "    @app.get('/health')\n"
        "    def health():\n"
        "        return {'status': 'ok'}\n\n"
        "    return app\n",
        encoding="utf-8",
    )

    result = PythonCodeGraphAdapter().extract_file(
        task_id="task-1",
        repo_root=repo_root,
        file_path=file_path,
    )

    symbols_by_name = {symbol.qualified_name: symbol for symbol in result.symbols}
    assert "app.main.create_app" in symbols_by_name
    assert "app.main.create_app.health" in symbols_by_name
    assert any(symbol.symbol_kind == "route" and symbol.name == "GET /health" for symbol in result.symbols)

    create_app_id = symbols_by_name["app.main.create_app"].symbol_id
    health_id = symbols_by_name["app.main.create_app.health"].symbol_id
    route_id = next(
        symbol.symbol_id
        for symbol in result.symbols
        if symbol.symbol_kind == "route" and symbol.name == "GET /health"
    )
    edge_pairs = {(edge.edge_kind, edge.from_symbol_id, edge.to_symbol_id) for edge in result.edges}

    assert ("contains", create_app_id, health_id) in edge_pairs
    assert ("routes_to", route_id, health_id) in edge_pairs
