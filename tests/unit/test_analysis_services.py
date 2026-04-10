from app.services.analyzers.backend_analyzer import BackendAnalyzer
from app.services.analyzers.deploy_analyzer import DeployAnalyzer
from app.services.analyzers.frontend_analyzer import FrontendAnalyzer
from app.services.analyzers.logic_mapper import LogicMapper
from app.services.analyzers.stack_detector import StackDetector


def test_stack_detector_identifies_fastapi_and_react():
    summary = StackDetector().detect(
        ["pyproject.toml", "package.json"],
        {"pyproject.toml": "fastapi", "package.json": '{"dependencies":{"react":"18.2.0"}}'},
    )
    assert set(summary) == {"frameworks", "languages"}
    assert "fastapi" in summary["frameworks"]
    assert "react" in summary["frameworks"]
    assert "python" in summary["languages"]
    assert "javascript" in summary["languages"]


def test_stack_detector_detects_nested_manifests():
    summary = StackDetector().detect(
        ["services/api/pyproject.toml", "apps/web/package.json", "apps/web/src/App.tsx"],
        {
            "services/api/pyproject.toml": "fastapi",
            "apps/web/package.json": '{"dependencies":{"react":"18.2.0"}}',
        },
    )
    assert "fastapi" in summary["frameworks"]
    assert "react" in summary["frameworks"]
    assert "python" in summary["languages"]
    assert "typescript" in summary["languages"]


def test_backend_and_frontend_analysis_feed_logic_mapper():
    backend = BackendAnalyzer().analyze(
        {"app/main.py": "@app.get('/api/v1/items')\nasync def items():\n    return []\n"}
    )
    frontend = FrontendAnalyzer().analyze(
        {
            "package.json": '{"dependencies":{"react":"18.2.0","zustand":"4.5.0"}}',
            "src/App.tsx": (
                "import { BrowserRouter, Route } from 'react-router-dom'\n"
                "import { Header } from './Header'\n"
                "fetch('/api/v1/items')\n"
                "<Route path=\"/items\" element={<div />} />\n"
            ),
        }
    )
    flows = LogicMapper().map_flows(frontend, backend)
    assert backend["routes"][0]["path"] == "/api/v1/items"
    assert frontend["api_calls"][0]["url"] == "/api/v1/items"
    assert frontend["framework"] == "react"
    assert frontend["state_manager"] == "zustand"
    assert frontend["components"][0]["name"] == "App"
    assert "Header" in frontend["components"][0]["imports"]
    assert frontend["api_calls"][0]["client"] == "fetch"
    assert frontend["api_calls"][0]["method"] == "GET"
    assert flows["flows"][0]["backend_route"] == "/api/v1/items"
    assert set(flows["flows"][0]) == {
        "frontend_call",
        "frontend_source",
        "backend_route",
        "backend_source",
        "backend_method",
        "confidence",
    }


def test_logic_mapper_keeps_duplicate_backend_routes_for_same_path():
    backend = BackendAnalyzer().analyze(
        {
            "app/main.py": (
                "@app.get('/api/v1/items')\nasync def list_items():\n    return []\n"
                "@app.post('/api/v1/items')\nasync def create_item():\n    return {}\n"
            )
        }
    )
    frontend = FrontendAnalyzer().analyze({"src/App.tsx": "fetch('/api/v1/items')\n"})
    flows = LogicMapper().map_flows(frontend, backend)

    assert [route["method"] for route in backend["routes"]] == ["GET", "POST"]
    assert len(flows["flows"]) == 2
    assert [flow["backend_method"] for flow in flows["flows"]] == ["GET", "POST"]
    assert all(flow["backend_route"] == "/api/v1/items" for flow in flows["flows"])
    assert all(flow["confidence"] == 1.0 for flow in flows["flows"])


def test_deploy_analyzer_extracts_compose_env_and_kubernetes_metadata():
    summary = DeployAnalyzer().analyze(
        ["docker-compose.yml", ".env.example", "k8s/api.yaml"],
        {
            "docker-compose.yml": (
                "services:\n"
                "  redis:\n"
                "    image: redis:7-alpine\n"
                "    ports:\n"
                "      - \"6379:6379\"\n"
                "  api:\n"
                "    build: .\n"
                "    ports:\n"
                "      - \"8000:8000\"\n"
                "    depends_on:\n"
                "      - redis\n"
            ),
            ".env.example": "REDIS_URL=redis://redis:6379/0\nAPI_KEYS=\n",
            "k8s/api.yaml": (
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: api\n"
            ),
        },
    )

    assert [service["name"] for service in summary["services"]] == ["redis", "api"]
    assert summary["services"][1]["depends_on"] == ["redis"]
    assert summary["environment_files"] == [".env.example"]
    assert summary["environment_variables"][0]["key"] == "REDIS_URL"
    assert summary["kubernetes_resources"][0] == {
        "kind": "Deployment",
        "name": "api",
        "source_file": "k8s/api.yaml",
    }


def test_deploy_analyzer_ignores_helm_templates_that_are_not_plain_yaml():
    summary = DeployAnalyzer().analyze(
        [
            "ops/helm/learn-new/templates/configmap.yaml",
            "ops/k8s/deployment.yaml",
        ],
        {
            "ops/helm/learn-new/templates/configmap.yaml": (
                "apiVersion: v1\n"
                "kind: ConfigMap\n"
                "metadata:\n"
                "  name: {{ .Release.Name }}-config\n"
                "data:\n"
                "  EXAMPLE: {{ .Values.example | quote }}\n"
            ),
            "ops/k8s/deployment.yaml": (
                "apiVersion: apps/v1\n"
                "kind: Deployment\n"
                "metadata:\n"
                "  name: api\n"
            ),
        },
    )

    assert summary["manifests"] == [
        "ops/helm/learn-new/templates/configmap.yaml",
        "ops/k8s/deployment.yaml",
    ]
    assert summary["kubernetes_resources"] == [
        {
            "kind": "Deployment",
            "name": "api",
            "source_file": "ops/k8s/deployment.yaml",
        }
    ]
