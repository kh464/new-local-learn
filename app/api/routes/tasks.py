from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from app.core.models import AnalyzeRequest, TaskStatus
from app.storage.task_store import RedisTaskStore

router = APIRouter()


def get_task_store(request: Request) -> RedisTaskStore:
    store = getattr(request.app.state, "task_store", None)
    if store is None:
        raise RuntimeError("Task store is not configured.")
    return store


async def enqueue_analysis(task_id: str, github_url: str) -> str:
    return task_id


@router.post("/analyze", status_code=202)
async def analyze(request: AnalyzeRequest) -> dict[str, str]:
    task_id = uuid4().hex
    await enqueue_analysis(task_id=task_id, github_url=str(request.github_url))
    return {
        "task_id": task_id,
        "status_url": f"/api/v1/tasks/{task_id}",
        "result_url": f"/api/v1/tasks/{task_id}/result",
        "stream_url": f"/api/v1/tasks/{task_id}/stream",
    }


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def task_status(task_id: str, store: RedisTaskStore = Depends(get_task_store)) -> TaskStatus:
    status = await store.get_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return status


@router.get("/tasks/{task_id}/result")
async def task_result(task_id: str, store: RedisTaskStore = Depends(get_task_store)) -> dict[str, object]:
    result = await store.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task result not found.")
    return {"task_id": task_id, "result": result}


@router.get("/tasks/{task_id}/stream")
async def task_stream(task_id: str, store: RedisTaskStore = Depends(get_task_store)) -> dict[str, object]:
    events = await store.get_events(task_id)
    return {"task_id": task_id, "events": events}
