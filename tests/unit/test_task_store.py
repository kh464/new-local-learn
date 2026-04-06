from app.core.models import TaskState, TaskStatus
from app.storage.task_store import RedisTaskStore


async def test_task_store_round_trip(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-1", state=TaskState.QUEUED))
    loaded = await store.get_status("task-1")
    assert loaded is not None
    assert loaded.state is TaskState.QUEUED
