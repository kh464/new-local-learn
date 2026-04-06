from app.services.analyzers.tutor_composer import TutorComposer
from app.services.docs.markdown_compiler import MarkdownCompiler
from app.services.docs.mermaid_builder import MermaidBuilder


def test_mermaid_builder_reflects_detected_repo_stack():
    mermaid = MermaidBuilder().build_system_diagram({"frameworks": ["fastapi", "react"]})

    assert "React UI" in mermaid
    assert "FastAPI API" in mermaid
    assert "Worker" not in mermaid
    assert "Redis" not in mermaid


def test_markdown_compiler_includes_mermaid_and_routes():
    tutorial = TutorComposer().compose({"frameworks": ["fastapi", "react"]}, {"flows": []})
    mermaid = MermaidBuilder().build_system_diagram({"frameworks": ["fastapi", "react"]})
    markdown = MarkdownCompiler().compile(
        task_id="task-1",
        repo_summary={"name": "demo", "key_files": ["app/main.py"]},
        detected_stack={"frameworks": ["fastapi", "react"]},
        backend_summary={"routes": [{"method": "GET", "path": "/health"}]},
        frontend_summary={"routing": "react-router-dom", "api_calls": []},
        logic_summary={"flows": []},
        tutorial_summary=tutorial,
        mermaid_sections={"system": mermaid},
    )

    assert "```mermaid" in markdown
    assert "/health" in markdown
