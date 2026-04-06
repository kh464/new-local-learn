from app.core.models import TaskState, TaskStatus
from app.storage.task_store import RedisTaskStore


async def test_result_endpoint_returns_accepted_until_complete(api_client, fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-1", state=TaskState.RUNNING, progress=42))

    response = await api_client.get("/api/v1/tasks/task-1/result")

    assert response.status_code == 202
    assert response.json() == {"task_id": "task-1", "state": "running"}
