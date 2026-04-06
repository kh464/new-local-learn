from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.models import AnalysisResult, AnalyzeRequest, TaskState, TaskStatus
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


@router.get("/tasks/{task_id}/result", response_model=AnalysisResult)
async def task_result(task_id: str, store: RedisTaskStore = Depends(get_task_store)) -> AnalysisResult | JSONResponse:
    result = await store.get_result(task_id)
    if result is not None:
        return result

    status_payload = await store.get_status(task_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    if status_payload.state in {TaskState.QUEUED, TaskState.RUNNING}:
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"task_id": task_id, "state": status_payload.state.value},
        )

    if status_payload.state in {TaskState.FAILED, TaskState.CANCELLED}:
        content: dict[str, str] = {"task_id": task_id, "state": status_payload.state.value}
        if status_payload.error is not None:
            content["error"] = status_payload.error
        return JSONResponse(status_code=status.HTTP_200_OK, content=content)

    raise HTTPException(status_code=404, detail="Task result not found.")


@router.get("/tasks/{task_id}/stream")
async def task_stream(task_id: str, store: RedisTaskStore = Depends(get_task_store)) -> StreamingResponse:
    events = await store.get_events(task_id)

    async def event_stream():
        for event in events:
            yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
