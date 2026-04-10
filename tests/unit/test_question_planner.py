from __future__ import annotations

import json

from app.services.knowledge.question_planner import QuestionPlanner
from app.services.knowledge.repo_map_loader import RepoMapLoader


def test_question_planner_prefers_call_chain_and_entrypoints(tmp_path):
    repo_map_path = tmp_path / "repo_map.json"
    repo_map_path.write_text(
        json.dumps(
            {
                "task_id": "task-1",
                "file_nodes": [
                    {"id": "file:app/main.py", "file_path": "app/main.py", "language": "python", "layer": "backend"},
                    {"id": "file:web/src/main.ts", "file_path": "web/src/main.ts", "language": "typescript", "layer": "frontend"},
                ],
                "symbol_nodes": [
                    {
                        "id": "symbol:app/api/routes.py:list_tasks",
                        "file_path": "app/api/routes.py",
                        "name": "list_tasks",
                        "kind": "function",
                        "line": 5,
                        "route_path": "/api/tasks",
                        "route_method": "GET",
                    },
                    {
                        "id": "symbol:app/services/knowledge/index_builder.py:KnowledgeIndexBuilder",
                        "file_path": "app/services/knowledge/index_builder.py",
                        "name": "KnowledgeIndexBuilder",
                        "kind": "class",
                        "line": 10,
                    },
                ],
                "edges": [
                    {
                        "type": "maps_to_backend",
                        "source": "file:web/src/App.vue",
                        "target": "symbol:app/api/routes.py:list_tasks",
                        "path": "/api/tasks",
                        "method": "GET",
                        "frontend_file": "web/src/App.vue",
                        "backend_file": "app/api/routes.py",
                    }
                ],
                "entrypoints": {
                    "backend": {"file_path": "app/main.py", "language": "python", "layer": "backend"},
                    "frontend": {"file_path": "web/src/main.ts", "language": "typescript", "layer": "frontend"},
                },
                "call_chains": [
                    {
                        "summary": "web/src/App.vue -> GET /api/tasks -> app/api/routes.py:list_tasks",
                        "frontend_file": "web/src/App.vue",
                        "backend_file": "app/api/routes.py",
                        "route_path": "/api/tasks",
                        "method": "GET",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    payload = RepoMapLoader().load(repo_map_path)
    planner = QuestionPlanner(payload)

    entry_plan = planner.plan("这个仓库的后端入口在哪里？")
    assert entry_plan.question_type == "entrypoint"
    assert entry_plan.entrypoint_hits[0]["file_path"] == "app/main.py"

    call_chain_plan = planner.plan("前端请求是如何到后端的？")
    assert call_chain_plan.question_type == "call_chain"
    assert call_chain_plan.call_chain_hits[0]["route_path"] == "/api/tasks"

    capability_plan = planner.plan("项目里是否存在知识库？")
    assert capability_plan.question_type == "capability"
    assert capability_plan.symbol_hits[0]["name"] == "KnowledgeIndexBuilder"
