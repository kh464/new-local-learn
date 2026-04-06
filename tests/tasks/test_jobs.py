import pytest

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
    assert [status.stage for status in seen_statuses] == [
        TaskStage.FETCH_REPO,
        TaskStage.SCAN_TREE,
        TaskStage.DETECT_STACK,
        TaskStage.ANALYZE_BACKEND,
        TaskStage.ANALYZE_FRONTEND,
        TaskStage.BUILD_DOC,
        TaskStage.FINALIZE,
    ]
    assert [status.progress for status in seen_statuses] == [5, 20, 35, 50, 65, 85, 100]
    assert seen_statuses[0].created_at == seen_statuses[1].created_at

    status = await store.get_status("task-1")
    assert status is not None
    assert status.state is TaskState.SUCCEEDED
    assert status.stage is TaskStage.FINALIZE
    assert status.progress == 100

    result_payload = await store.get_result("task-1")
    assert result_payload["github_url"] == github_url
    assert result_payload["markdown_path"].endswith("result.md")
    assert result_payload["repo_summary"]["key_files"] == ["package.json", "pyproject.toml"]
    assert "fastapi" in result_payload["detected_stack"]["frameworks"]
    assert "react" in result_payload["detected_stack"]["frameworks"]
    assert result_payload["backend_summary"]["routes"][0]["path"] == "/health"
    assert result_payload["frontend_summary"]["api_calls"][0]["url"] == "/health"
    assert result_payload["logic_summary"]["flows"][0]["backend_route"] == "/health"
    assert result_payload["tutorial_summary"]["run_steps"]
    assert "React UI" in result_payload["mermaid_sections"]["system"]

    events = await store.get_events("task-1")
    assert [event["stage"] for event in events] == [
        TaskStage.FETCH_REPO.value,
        TaskStage.SCAN_TREE.value,
        TaskStage.DETECT_STACK.value,
        TaskStage.ANALYZE_BACKEND.value,
        TaskStage.ANALYZE_FRONTEND.value,
        TaskStage.BUILD_DOC.value,
        TaskStage.FINALIZE.value,
    ]
    assert [event["progress"] for event in events] == [5, 20, 35, 50, 65, 85, 100]
    assert [event["state"] for event in events[:-1]] == [TaskState.RUNNING.value] * 6
    assert events[-1]["state"] == TaskState.SUCCEEDED.value


async def test_run_analysis_job_marks_failed_on_error(fake_job_context):
    store = fake_job_context["task_store"]
    seen_statuses = []
    original_set_status = store.set_status

    async def set_status_spy(status):
        seen_statuses.append(status)
        await original_set_status(status)

    async def set_result_fail(task_id, result):
        raise RuntimeError("boom")

    store.set_status = set_status_spy
    store.set_result = set_result_fail
    github_url = "https://github.com/octocat/Hello-World"

    result = await run_analysis_job(fake_job_context, "task-2", github_url)

    assert result["task_id"] == "task-2"
    assert result["state"] == TaskState.FAILED.value
    assert [status.stage for status in seen_statuses[:-1]] == [
        TaskStage.FETCH_REPO,
        TaskStage.SCAN_TREE,
        TaskStage.DETECT_STACK,
        TaskStage.ANALYZE_BACKEND,
        TaskStage.ANALYZE_FRONTEND,
        TaskStage.BUILD_DOC,
    ]
    assert seen_statuses[-1].stage is TaskStage.FINALIZE
    assert seen_statuses[0].created_at == seen_statuses[1].created_at

    status = await store.get_status("task-2")
    assert status is not None
    assert status.state is TaskState.FAILED
    assert status.stage is TaskStage.FINALIZE
    assert status.progress == 100
    assert status.error == "boom"

    result_payload = await store.get_result("task-2")
    assert result_payload is None

    events = await store.get_events("task-2")
    assert [event["stage"] for event in events[:-1]] == [
        TaskStage.FETCH_REPO.value,
        TaskStage.SCAN_TREE.value,
        TaskStage.DETECT_STACK.value,
        TaskStage.ANALYZE_BACKEND.value,
        TaskStage.ANALYZE_FRONTEND.value,
        TaskStage.BUILD_DOC.value,
    ]
    assert events[-1] == {
        "state": TaskState.FAILED.value,
        "stage": TaskStage.FINALIZE.value,
        "progress": 100,
        "error": "boom",
    }
