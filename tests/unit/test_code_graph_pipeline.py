from __future__ import annotations

from app.services.code_graph.pipeline import CodeGraphBuildPipeline
from app.services.code_graph.storage import CodeGraphStore


def test_code_graph_pipeline_builds_python_repo_into_sqlite(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "app" / "api").mkdir(parents=True)
    (repo_root / "app" / "services").mkdir(parents=True)

    (repo_root / "app" / "api" / "routes.py").write_text(
        "from fastapi import APIRouter\n"
        "from app.services.reporting import generate_report\n\n"
        "router = APIRouter()\n\n"
        "@router.get('/tasks')\n"
        "async def list_tasks():\n"
        "    return generate_report()\n",
        encoding="utf-8",
    )
    (repo_root / "app" / "services" / "reporting.py").write_text(
        "def generate_report():\n"
        "    return {'ok': True}\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "knowledge.db"
    pipeline = CodeGraphBuildPipeline()

    build_result = pipeline.build(
        task_id="task-graph-1",
        repo_root=repo_root,
        db_path=db_path,
    )

    graph_store = CodeGraphStore(db_path)
    files = graph_store.list_files(task_id="task-graph-1")
    symbols = graph_store.list_symbols(task_id="task-graph-1")

    assert build_result.files_count == 2
    assert build_result.symbols_count >= 3
    assert build_result.edges_count >= 4
    assert any(file.path == "app/api/routes.py" for file in files)
    assert any(symbol.qualified_name == "app.api.routes.list_tasks" for symbol in symbols)
    assert any(symbol.qualified_name == "app.services.reporting.generate_report" for symbol in symbols)
    assert any(file.summary_zh for file in files)
    assert any(symbol.summary_zh for symbol in symbols)
