from app.tasks.jobs import run_analysis_job


async def test_pipeline_returns_result_payload(fake_job_context):
    result = await run_analysis_job(fake_job_context, "task-1", "https://github.com/octocat/Hello-World")

    assert result["state"] == "succeeded"
    assert result["result"]["markdown_path"].endswith("result.md")
