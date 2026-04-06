from app.core.models import TaskState, TaskStatus
from app.storage.task_store import RedisTaskStore


async def test_analyze_endpoint_returns_urls(api_client, monkeypatch):
    async def fake_enqueue(task_id: str, github_url: str) -> str:
        return task_id

    monkeypatch.setattr("app.api.routes.tasks.enqueue_analysis", fake_enqueue)
    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )
    assert response.status_code == 202
    payload = response.json()
    task_id = payload["task_id"]
    assert payload["status_url"] == f"/api/v1/tasks/{task_id}"
    assert payload["result_url"] == f"/api/v1/tasks/{task_id}/result"
    assert payload["stream_url"] == f"/api/v1/tasks/{task_id}/stream"


async def test_task_endpoints_return_status_result_and_events(api_client, fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    status = TaskStatus(task_id="task-2", state=TaskState.RUNNING, progress=42)
    await store.set_status(status)
    await store.set_result("task-2", {"doc": "ready"})
    await store.append_event("task-2", {"message": "started"})

    status_response = await api_client.get("/api/v1/tasks/task-2")
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "running"

    result_response = await api_client.get("/api/v1/tasks/task-2/result")
    assert result_response.status_code == 200
    assert result_response.json()["result"] == {"doc": "ready"}

    stream_response = await api_client.get("/api/v1/tasks/task-2/stream")
    assert stream_response.status_code == 200
    assert stream_response.json()["events"] == [{"message": "started"}]
