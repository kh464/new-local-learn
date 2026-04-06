from app.services.analyzers.backend_analyzer import BackendAnalyzer
from app.services.analyzers.frontend_analyzer import FrontendAnalyzer
from app.services.analyzers.logic_mapper import LogicMapper
from app.services.analyzers.stack_detector import StackDetector


def test_stack_detector_identifies_fastapi_and_react():
    summary = StackDetector().detect(
        ["pyproject.toml", "package.json"],
        {"pyproject.toml": "fastapi", "package.json": '{"dependencies":{"react":"18.2.0"}}'},
    )
    assert "fastapi" in summary["frameworks"]
    assert "react" in summary["frameworks"]


def test_backend_and_frontend_analysis_feed_logic_mapper():
    backend = BackendAnalyzer().analyze(
        {"app/main.py": "@app.get('/api/v1/items')\nasync def items():\n    return []\n"}
    )
    frontend = FrontendAnalyzer().analyze({"src/App.tsx": "fetch('/api/v1/items')\n"})
    flows = LogicMapper().map_flows(frontend, backend)
    assert backend["routes"][0]["path"] == "/api/v1/items"
    assert frontend["api_calls"][0]["url"] == "/api/v1/items"
    assert flows["flows"][0]["backend_route"] == "/api/v1/items"
