from app.core.models import TaskState
from app.tasks.jobs import run_analysis_job


async def test_run_analysis_job_sets_succeeded(fake_job_context):
    result = await run_analysis_job(
        fake_job_context,
        "task-1",
        "https://github.com/octocat/Hello-World",
    )
    assert result["task_id"] == "task-1"
    assert result["state"] == TaskState.SUCCEEDED.value
