from __future__ import annotations

import json

from app.services.knowledge.repo_map_builder import RepoMapBuilder


def test_repo_map_builder_extracts_nodes_edges_and_entrypoints(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app" / "api").mkdir(parents=True)
    (repo_path / "web" / "src").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from app.api.routes import router\n\n"
        "app = FastAPI()\n"
        "app.include_router(router, prefix='/api/v1')\n",
        encoding="utf-8",
    )
    (repo_path / "app" / "api" / "routes.py").write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n"
        "@router.get('/tasks')\n"
        "async def list_tasks():\n"
        "    return {'items': []}\n",
        encoding="utf-8",
    )
    (repo_path / "web" / "src" / "main.ts").write_text(
        "import App from './App.vue'\n"
        "import { createApp } from 'vue'\n\n"
        "createApp(App).mount('#app')\n",
        encoding="utf-8",
    )
    (repo_path / "web" / "src" / "App.vue").write_text(
        "<script setup lang=\"ts\">\n"
        "const loadTasks = async () => {\n"
        "  const response = await fetch('/api/v1/tasks')\n"
        "  return response.json()\n"
        "}\n"
        "</script>\n"
        "<template><button @click=\"loadTasks\">Load</button></template>\n",
        encoding="utf-8",
    )

    repo_map_path = tmp_path / "repo_map.json"
    result = RepoMapBuilder().build(task_id="task-1", repo_path=repo_path, output_path=repo_map_path)

    assert repo_map_path.is_file()
    assert result["task_id"] == "task-1"
    assert result["entrypoints"]["backend"]["file_path"] == "app/main.py"
    assert result["entrypoints"]["frontend"]["file_path"] == "web/src/main.ts"
    assert any(node["file_path"] == "app/main.py" for node in result["file_nodes"])
    assert any(node["name"] == "list_tasks" for node in result["symbol_nodes"])
    assert any(edge["type"] == "imports" for edge in result["edges"])
    assert any(edge["type"] == "maps_to_backend" for edge in result["edges"])
    assert any("/api/v1/tasks" in chain["summary"] for chain in result["call_chains"])

    payload = json.loads(repo_map_path.read_text(encoding="utf-8"))
    assert payload["entrypoints"]["backend"]["file_path"] == "app/main.py"


def test_repo_map_builder_captures_frontend_handler_for_vue_request(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app" / "api").mkdir(parents=True)
    (repo_path / "web" / "src").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from app.api.routes import router\n\n"
        "app = FastAPI()\n"
        "app.include_router(router, prefix='/api/v1')\n",
        encoding="utf-8",
    )
    (repo_path / "app" / "api" / "routes.py").write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n"
        "@router.get('/tasks')\n"
        "async def list_tasks():\n"
        "    return {'items': []}\n",
        encoding="utf-8",
    )
    (repo_path / "web" / "src" / "App.vue").write_text(
        "<script setup lang=\"ts\">\n"
        "const loadTasks = async () => {\n"
        "  const response = await fetch('/api/v1/tasks')\n"
        "  return response.json()\n"
        "}\n"
        "</script>\n"
        "<template><button @click=\"loadTasks\">Load</button></template>\n",
        encoding="utf-8",
    )

    result = RepoMapBuilder().build(
        task_id="task-front-handler",
        repo_path=repo_path,
        output_path=tmp_path / "repo_map.json",
    )

    assert any(
        edge["type"] == "maps_to_backend"
        and edge.get("frontend_symbol") == "loadTasks"
        and edge.get("frontend_trigger") == "click"
        for edge in result["edges"]
    )
    assert any(
        chain["summary"] == "web/src/App.vue:loadTasks [click] -> GET /api/v1/tasks -> app/api/routes.py:list_tasks"
        for chain in result["call_chains"]
    )


def test_repo_map_builder_expands_frontend_component_mount_chain(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app" / "api").mkdir(parents=True)
    (repo_path / "web" / "src" / "components").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from app.api.routes import router\n\n"
        "app = FastAPI()\n"
        "app.include_router(router, prefix='/api/v1')\n",
        encoding="utf-8",
    )
    (repo_path / "app" / "api" / "routes.py").write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n"
        "@router.get('/tasks')\n"
        "async def list_tasks():\n"
        "    return {'items': []}\n",
        encoding="utf-8",
    )
    (repo_path / "web" / "src" / "main.ts").write_text(
        "import App from './App.vue'\n"
        "import { createApp } from 'vue'\n\n"
        "createApp(App).mount('#app')\n",
        encoding="utf-8",
    )
    (repo_path / "web" / "src" / "App.vue").write_text(
        "<script setup lang=\"ts\">\n"
        "import TaskList from './components/TaskList.vue'\n"
        "</script>\n"
        "<template><TaskList /></template>\n",
        encoding="utf-8",
    )
    (repo_path / "web" / "src" / "components" / "TaskList.vue").write_text(
        "<script setup lang=\"ts\">\n"
        "const loadTasks = async () => {\n"
        "  const response = await fetch('/api/v1/tasks')\n"
        "  return response.json()\n"
        "}\n"
        "</script>\n"
        "<template><button @click=\"loadTasks\">Load</button></template>\n",
        encoding="utf-8",
    )

    result = RepoMapBuilder().build(
        task_id="task-component-chain",
        repo_path=repo_path,
        output_path=tmp_path / "repo_map.json",
    )

    assert any(
        chain["summary"]
        == "web/src/main.ts -> web/src/App.vue -> web/src/components/TaskList.vue:loadTasks [click] -> GET /api/v1/tasks -> app/api/routes.py:list_tasks"
        for chain in result["call_chains"]
    )


def test_repo_map_builder_maps_wrapped_frontend_requests_to_parameterized_backend_routes(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app" / "api").mkdir(parents=True)
    (repo_path / "web" / "src").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from app.api.routes import router\n\n"
        "app = FastAPI()\n"
        "app.include_router(router, prefix='/api/v1')\n",
        encoding="utf-8",
    )
    (repo_path / "app" / "api" / "routes.py").write_text(
        "from fastapi import APIRouter\n\n"
        "router = APIRouter()\n\n"
        "@router.post('/tasks/{task_id}/chat')\n"
        "async def task_chat(task_id: str):\n"
        "    return {'task_id': task_id}\n",
        encoding="utf-8",
    )
    (repo_path / "web" / "src" / "api.ts").write_text(
        "export async function submitTaskQuestion(taskId: string) {\n"
        "  return requestJson(`/api/v1/tasks/${taskId}/chat`)\n"
        "}\n",
        encoding="utf-8",
    )

    result = RepoMapBuilder().build(
        task_id="task-dynamic",
        repo_path=repo_path,
        output_path=tmp_path / "repo_map.json",
    )

    assert any(edge["type"] == "maps_to_backend" for edge in result["edges"])
    assert any("/api/v1/tasks/{taskId}/chat" in chain["summary"] for chain in result["call_chains"])


def test_repo_map_builder_extracts_backend_calls_for_multi_hop_chain(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app" / "api").mkdir(parents=True)
    (repo_path / "app" / "services").mkdir(parents=True)
    (repo_path / "web" / "src").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n"
        "from app.api.routes import router\n\n"
        "app = FastAPI()\n"
        "app.include_router(router, prefix='/api/v1')\n",
        encoding="utf-8",
    )
    (repo_path / "app" / "services" / "reporting.py").write_text(
        "def generate_report(task_id: str) -> dict:\n"
        "    return {'task_id': task_id}\n",
        encoding="utf-8",
    )
    (repo_path / "app" / "api" / "routes.py").write_text(
        "from fastapi import APIRouter\n"
        "from app.services.reporting import generate_report\n\n"
        "router = APIRouter()\n\n"
        "@router.post('/tasks/{task_id}/chat')\n"
        "async def task_chat(task_id: str):\n"
        "    return generate_report(task_id)\n",
        encoding="utf-8",
    )
    (repo_path / "web" / "src" / "api.ts").write_text(
        "export async function submitTaskQuestion(taskId: string) {\n"
        "  return requestJson(`/api/v1/tasks/${taskId}/chat`)\n"
        "}\n",
        encoding="utf-8",
    )

    result = RepoMapBuilder().build(
        task_id="task-multi-hop",
        repo_path=repo_path,
        output_path=tmp_path / "repo_map.json",
    )

    assert any(
        edge["type"] == "calls"
        and edge["source"] == "symbol:app/api/routes.py:task_chat"
        and edge["target"] == "symbol:app/services/reporting.py:generate_report"
        for edge in result["edges"]
    )
    assert any(
        chain["summary"]
        == "web/src/api.ts -> POST /api/v1/tasks/{taskId}/chat -> app/api/routes.py:task_chat -> app/services/reporting.py:generate_report"
        for chain in result["call_chains"]
    )


def test_repo_map_builder_skips_temp_and_generated_directories(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app").mkdir(parents=True)
    (repo_path / "tmpbase" / "noise").mkdir(parents=True)
    (repo_path / "node_modules" / "pkg").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (repo_path / "tmpbase" / "noise" / "demo.py").write_text("def noisy():\n    return True\n", encoding="utf-8")
    (repo_path / "node_modules" / "pkg" / "index.js").write_text("export const noisy = true\n", encoding="utf-8")

    result = RepoMapBuilder().build(
        task_id="task-clean",
        repo_path=repo_path,
        output_path=tmp_path / "repo_map.json",
    )

    file_paths = [node["file_path"] for node in result["file_nodes"]]
    assert "app/main.py" in file_paths
    assert all(not str(path).startswith("tmpbase/") for path in file_paths)
    assert all(not str(path).startswith("node_modules/") for path in file_paths)


def test_repo_map_builder_skips_nested_git_repositories(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app").mkdir(parents=True)
    (repo_path / "nested-ui").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (repo_path / "nested-ui" / ".git").write_text("gitdir: ../.git/worktrees/nested-ui\n", encoding="utf-8")
    (repo_path / "nested-ui" / "api.ts").write_text("export async function demo() {}\n", encoding="utf-8")

    result = RepoMapBuilder().build(
        task_id="task-nested",
        repo_path=repo_path,
        output_path=tmp_path / "repo_map.json",
    )

    file_paths = [node["file_path"] for node in result["file_nodes"]]
    assert "app/main.py" in file_paths
    assert all(not str(path).startswith("nested-ui/") for path in file_paths)


def test_repo_map_builder_skips_test_directories_and_spec_files(tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / "app").mkdir(parents=True)
    (repo_path / "tests").mkdir(parents=True)
    (repo_path / "web" / "src").mkdir(parents=True)

    (repo_path / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (repo_path / "tests" / "test_api.py").write_text("def test_api():\n    assert True\n", encoding="utf-8")
    (repo_path / "web" / "src" / "api.spec.ts").write_text("export const noisy = true\n", encoding="utf-8")

    result = RepoMapBuilder().build(
        task_id="task-tests",
        repo_path=repo_path,
        output_path=tmp_path / "repo_map.json",
    )

    file_paths = [node["file_path"] for node in result["file_nodes"]]
    assert "app/main.py" in file_paths
    assert all(not str(path).startswith("tests/") for path in file_paths)
    assert "web/src/api.spec.ts" not in file_paths
