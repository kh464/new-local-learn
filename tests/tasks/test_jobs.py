from app.core.models import TaskStage, TaskState
from app.tasks.jobs import run_analysis_job


async def test_run_analysis_job_sets_succeeded(fake_job_context):
    store = fake_job_context["task_store"]
    seen_statuses = []
    original_set_status = store.set_status

    async def set_status_spy(status):
        seen_statuses.append(status)
        await original_set_status(status)

    store.set_status = set_status_spy
    github_url = "https://github.com/octocat/Hello-World"
    result = await run_analysis_job(fake_job_context, "task-1", github_url)

    assert result["task_id"] == "task-1"
    assert result["state"] == TaskState.SUCCEEDED.value
    assert len(seen_statuses) == 2
    assert seen_statuses[0].created_at == seen_statuses[1].created_at

    status = await store.get_status("task-1")
    assert status is not None
    assert status.state is TaskState.SUCCEEDED
    assert status.stage is TaskStage.FINALIZE
    assert status.progress == 100

    result_payload = await store.get_result("task-1")
    assert result_payload == {"github_url": github_url}

    events = await store.get_events("task-1")
    assert events == [
        {
            "state": TaskState.RUNNING.value,
            "stage": TaskStage.FETCH_REPO.value,
            "progress": 10,
        },
        {
            "state": TaskState.SUCCEEDED.value,
            "stage": TaskStage.FINALIZE.value,
            "progress": 100,
        },
    ]
