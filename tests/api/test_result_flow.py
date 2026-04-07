import httpx

from app.core.models import TaskState, TaskStatus
from app.main import create_app
from app.tasks.jobs import run_analysis_job
from app.storage.task_store import RedisTaskStore


async def test_result_endpoint_returns_accepted_until_complete(api_client, fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-1", state=TaskState.RUNNING, progress=42))

    response = await api_client.get("/api/v1/tasks/task-1/result")

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-1", "state": "running"}


async def test_analyze_flow_runs_job_and_exposes_result_artifacts(fake_job_context):
    store = fake_job_context["task_store"]
    app = create_app(task_store=store)
    app.state.settings.artifacts_dir = fake_job_context["settings"].artifacts_dir
    app.state.settings.max_file_count = fake_job_context["settings"].max_file_count
    app.state.settings.max_file_bytes = fake_job_context["settings"].max_file_bytes
    app.state.settings.max_total_bytes = fake_job_context["settings"].max_total_bytes
    app.state.settings.api_keys = ("e2e-secret",)

    class InlineQueue:
        async def enqueue_job(self, job_name: str, task_id: str, github_url: str):
            assert job_name == "run_analysis_job"
            await run_analysis_job(
                {
                    **fake_job_context,
                    "task_store": store,
                    "settings": app.state.settings,
                },
                task_id,
                github_url,
            )
            return object()

    app.state.arq_redis = InlineQueue()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        analyze_response = await client.post(
            "/api/v1/analyze",
            json={"github_url": "https://github.com/octocat/Hello-World"},
            headers={"X-API-Key": "e2e-secret"},
        )

        assert analyze_response.status_code == 202
        payload = analyze_response.json()
        task_id = payload["task_id"]
        task_token = payload["task_token"]
        task_headers = {"X-Task-Token": task_token}

        status_response = await client.get(f"/api/v1/tasks/{task_id}", headers=task_headers)
        result_response = await client.get(f"/api/v1/tasks/{task_id}/result", headers=task_headers)
        markdown_response = await client.get(
            f"/api/v1/tasks/{task_id}/artifacts/markdown",
            headers=task_headers,
        )
        html_response = await client.get(
            f"/api/v1/tasks/{task_id}/artifacts/html",
            headers=task_headers,
        )
        pdf_response = await client.get(
            f"/api/v1/tasks/{task_id}/artifacts/pdf",
            headers=task_headers,
        )

    assert status_response.status_code == 200
    assert status_response.json()["state"] == "succeeded"

    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["github_url"] == "https://github.com/octocat/Hello-World"
    assert result_payload["markdown_path"].endswith("result.md")
    assert result_payload["html_path"].endswith("result.html")
    assert result_payload["pdf_path"].endswith("result.pdf")

    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert "# Analysis Report" in markdown_response.text

    assert html_response.status_code == 200
    assert html_response.headers["content-type"].startswith("text/html")
    assert "<html" in html_response.text.lower()

    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"].startswith("application/pdf")
    assert pdf_response.content.startswith(b"%PDF-1.4")
