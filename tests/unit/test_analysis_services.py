from app.services.analyzers.backend_analyzer import BackendAnalyzer
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
    frontend = FrontendAnalyzer().analyze({"src/App.tsx": "fetch('/api/v1/items')\n"})
    flows = LogicMapper().map_flows(frontend, backend)
    assert backend["routes"][0]["path"] == "/api/v1/items"
    assert frontend["api_calls"][0]["url"] == "/api/v1/items"
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
