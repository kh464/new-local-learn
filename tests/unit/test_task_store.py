from app.core.models import TaskState, TaskStatus
from app.storage.task_store import RedisTaskStore


async def test_task_store_round_trip(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-1", state=TaskState.QUEUED))
    loaded = await store.get_status("task-1")
    assert loaded is not None
    assert loaded.state is TaskState.QUEUED


async def test_task_store_result_and_events(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_result("task-2", {"summary": "ok"})
    result = await store.get_result("task-2")
    assert result == {"summary": "ok"}

    await store.append_event("task-2", {"stage": "fetch_repo"})
    await store.append_event("task-2", {"stage": "scan_tree"})
    events = await store.get_events("task-2")
    assert events == [{"stage": "fetch_repo"}, {"stage": "scan_tree"}]
