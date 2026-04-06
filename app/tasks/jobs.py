from __future__ import annotations

from app.core.models import TaskStage, TaskState, TaskStatus
from app.storage.task_store import RedisTaskStore


def _get_task_store(ctx) -> RedisTaskStore:
    if isinstance(ctx, dict):
        store = ctx.get("task_store")
        if store is not None:
            return store
        redis = ctx.get("redis")
        if redis is not None:
            return RedisTaskStore(redis)
    store = getattr(ctx, "task_store", None)
    if store is not None:
        return store
    redis = getattr(ctx, "redis", None)
    if redis is not None:
        return RedisTaskStore(redis)
    raise RuntimeError("Task store is not available in job context.")


async def run_analysis_job(ctx, task_id: str, github_url: str) -> dict[str, str]:
    store = _get_task_store(ctx)
    running_status = TaskStatus(
        task_id=task_id,
        state=TaskState.RUNNING,
        stage=TaskStage.FETCH_REPO,
        progress=10,
    )
    await store.set_status(running_status)
    await store.append_event(
        task_id,
        {
            "state": TaskState.RUNNING.value,
            "stage": TaskStage.FETCH_REPO.value,
            "progress": 10,
        },
    )
    await store.set_result(task_id, {"github_url": github_url})
    succeeded_status = TaskStatus(
        task_id=task_id,
        state=TaskState.SUCCEEDED,
        stage=TaskStage.FINALIZE,
        progress=100,
        created_at=running_status.created_at,
    )
    await store.set_status(succeeded_status)
    await store.append_event(
        task_id,
        {
            "state": TaskState.SUCCEEDED.value,
            "stage": TaskStage.FINALIZE.value,
            "progress": 100,
        },
    )
    return {"task_id": task_id, "state": TaskState.SUCCEEDED.value}
