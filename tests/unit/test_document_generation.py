from app.services.analyzers.tutor_composer import TutorComposer
from app.services.docs.html_compiler import HtmlCompiler
from app.services.docs.markdown_compiler import MarkdownCompiler
from app.services.docs.mermaid_builder import MermaidBuilder
from app.services.docs.pdf_compiler import PdfCompiler


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
        frontend_summary={
            "framework": "react",
            "bundler": "vite",
            "state_manager": "zustand",
            "routing": [{"path": "/"}],
            "api_calls": [],
            "state_units": [],
            "components": [],
        },
        logic_summary={"flows": []},
        tutorial_summary=tutorial,
        deploy_summary={"services": [], "environment_files": [], "manifests": []},
        critique_summary={"coverage_notes": [], "inferred_sections": [], "missing_areas": []},
        mermaid_sections={"system": mermaid},
    )

    assert "```mermaid" in markdown
    assert "/health" in markdown
    assert "Framework: react" in markdown
    assert "Deploy Analysis" in markdown
    assert "Coverage Notes" in markdown


def test_html_compiler_wraps_markdown_in_html_document():
    html = HtmlCompiler().compile(title="Demo Report", markdown="# Heading\n\n- item")

    assert "<!doctype html>" in html.lower()
    assert "<h1>Demo Report</h1>" in html
    assert "<h1>Heading</h1>" in html
    assert "<ul>" in html
    assert "<li>item</li>" in html


def test_html_compiler_renders_code_fences_and_mermaid_blocks():
    html = HtmlCompiler().compile(
        title="Demo Report",
        markdown="## Diagram\n\n```mermaid\ngraph TD\nA-->B\n```\n\n```python\nprint('hi')\n```",
    )

    assert '<pre class="code-block mermaid"><code>' in html
    assert "graph TD" in html
    assert '<pre class="code-block"><code class="language-python">' in html
    assert "print" in html


def test_pdf_compiler_emits_pdf_bytes():
    pdf_bytes = PdfCompiler().compile(title="Demo Report", markdown="# Heading\n\n- item")

    assert pdf_bytes.startswith(b"%PDF-")
    assert b"Demo Report" in pdf_bytes


def test_pdf_compiler_wraps_long_lines_instead_of_truncating():
    long_line = ("alpha " * 24) + "TAILTOKEN"

    pdf_bytes = PdfCompiler().compile(title="Demo Report", markdown=long_line)

    assert b"TAILTOKEN" in pdf_bytes


def test_pdf_compiler_paginates_long_documents():
    markdown = "\n".join(f"Line {index}" for index in range(120))

    pdf_bytes = PdfCompiler().compile(title="Demo Report", markdown=markdown)

    assert pdf_bytes.count(b"/Type /Page /Parent") >= 2
