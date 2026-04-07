from app.core.models import AnalysisResult
from app.tasks.jobs import run_analysis_job


async def test_pipeline_returns_result_payload(fake_job_context):
    result = await run_analysis_job(fake_job_context, "task-1", "https://github.com/octocat/Hello-World")
    analysis_result = AnalysisResult.model_validate(result["result"])

    assert result["state"] == "succeeded"
    assert result["result"]["markdown_path"].endswith("result.md")
    assert result["result"]["html_path"].endswith("result.html")
    assert result["result"]["pdf_path"].endswith("result.pdf")
    assert result["result"]["repo_summary"]["key_files"] == ["package.json", "pyproject.toml"]
    assert result["result"]["backend_summary"]["routes"][0]["path"] == "/health"
    assert result["result"]["frontend_summary"]["api_calls"][0]["url"] == "/health"
    assert result["result"]["frontend_summary"]["framework"] == "react"
    assert result["result"]["frontend_summary"]["state_units"] == []
    assert result["result"]["logic_summary"]["flows"][0]["backend_route"] == "/health"
    assert result["result"]["tutorial_summary"]["run_steps"]
    assert result["result"]["tutorial_summary"]["request_lifecycle"]
    assert result["result"]["tutorial_summary"]["faq_entries"]
    assert result["result"]["deploy_summary"]["environment_files"] == [".env.example"]
    assert [service["name"] for service in result["result"]["deploy_summary"]["services"]] == ["redis", "api"]
    assert result["result"]["critique_summary"]["coverage_notes"]
    assert result["result"]["mermaid_sections"]["system"].startswith("graph TD")
    assert analysis_result.repo_summary.file_count == 7
    assert analysis_result.backend_summary.routes[0].path == "/health"
    assert analysis_result.frontend_summary.api_calls[0].url == "/health"
    assert analysis_result.frontend_summary.routing == []
    assert analysis_result.frontend_summary.framework == "react"
    assert analysis_result.logic_summary.flows[0].backend_method == "GET"
    assert analysis_result.tutorial_summary.mental_model
    assert [service.name for service in analysis_result.deploy_summary.services] == ["redis", "api"]
    assert analysis_result.critique_summary.missing_areas
    assert analysis_result.mermaid_sections.system.startswith("graph TD")
