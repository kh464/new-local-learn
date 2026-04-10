from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.core.audit import emit_audit_event
from app.core.models import (
    AnalysisResult,
    AnalyzeRequest,
    TaskListPage,
    TaskChatExchange,
    TaskChatHistory,
    TaskChatMessage,
    TaskChatRequest,
    TaskKnowledgeState,
    TaskStage,
    TaskState,
    TaskStatus,
)
from app.core.config import Settings
from app.core.security import require_api_key_scopes, require_task_access, require_task_access_scopes
from app.services.chat.answer_composer import AnswerComposer
from app.services.chat.answer_validator import AnswerValidator
from app.services.chat.evidence_assembler import EvidenceAssembler
from app.services.chat.llm_planning_agent import LlmPlanningAgent
from app.services.chat.mcp_gateway import McpGateway
from app.services.chat.mcp_tools import RepositoryQaToolSession
from app.services.chat.orchestrator import TaskChatOrchestrator
from app.services.chat.rule_fallback_planner import RuleFallbackPlanner
from app.services.llm.client import ChatCompletionClient
from app.services.llm.config import load_runtime_config
from app.services.llm.knowledge_chat import KnowledgeChatService
from app.services.repo.fetcher import normalize_github_url
from app.storage.artifacts import ArtifactPaths
from app.storage.task_store import RedisTaskStore

router = APIRouter()
_STREAM_POLL_INTERVAL_SECONDS = 0.1
_TERMINAL_STATES = {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED}
_ARTIFACT_SPECS = {
    "markdown": ("markdown_path", "text/markdown", "result.md"),
    "html": ("html_path", "text/html", "result.html"),
    "pdf": ("pdf_path", "application/pdf", "result.pdf"),
}


def get_task_store(request: Request) -> RedisTaskStore:
    store = getattr(request.app.state, "task_store", None)
    if store is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Task store is not configured.")
    return store


def get_job_queue(request: Request):
    queue = getattr(request.app.state, "arq_redis", None)
    if queue is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Task queue is not configured.")
    return queue


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Settings are not configured.")
    return settings


def _build_llm_client(settings: Settings) -> ChatCompletionClient | None:
    if not getattr(settings, "llm_enabled", False) or not settings.llm_config_path.is_file():
        return None
    try:
        runtime_config = load_runtime_config(settings.llm_config_path, settings.llm_profile)
    except Exception:
        return None
    return ChatCompletionClient(runtime_config)


async def _build_task_chat_orchestrator(
    *,
    task_id: str,
    db_path: Path | str,
    repo_map_path: Path | str | None,
    task_store: RedisTaskStore,
    planning_client: ChatCompletionClient | None,
    evidence_assembler: EvidenceAssembler,
    answer_composer: AnswerComposer,
    answer_validator: AnswerValidator,
) -> TaskChatOrchestrator:
    result = await task_store.get_result(task_id)
    repo_root = Path(result.repo_path) if result is not None else Path(db_path).parent
    session = RepositoryQaToolSession(
        task_id=task_id,
        repo_root=repo_root,
        repo_map_path=repo_map_path or (Path(db_path).parent / "repo_map.json"),
        knowledge_db_path=db_path,
        task_store=task_store,
    )
    return TaskChatOrchestrator(
        planning_agent=LlmPlanningAgent(client=planning_client) if planning_client is not None else None,
        fallback_planner=RuleFallbackPlanner(),
        mcp_gateway=McpGateway(session=session),
        evidence_assembler=evidence_assembler,
        answer_composer=answer_composer,
        answer_validator=answer_validator,
    )


def get_knowledge_chat_service(request: Request) -> KnowledgeChatService:
    service = getattr(request.app.state, "knowledge_chat_service", None)
    if service is not None:
        return service

    orchestrator = getattr(request.app.state, "task_chat_orchestrator", None)
    if orchestrator is not None:
        service = KnowledgeChatService(orchestrator=orchestrator)
        request.app.state.knowledge_chat_service = service
        return service

    settings = get_settings(request)
    task_store = get_task_store(request)
    planning_client = _build_llm_client(settings)
    evidence_assembler = EvidenceAssembler()
    answer_composer = AnswerComposer(client=planning_client)
    answer_validator = AnswerValidator()

    async def orchestrator_factory(**kwargs):
        return await _build_task_chat_orchestrator(
            task_id=str(kwargs["task_id"]),
            db_path=kwargs["db_path"],
            repo_map_path=kwargs.get("repo_map_path"),
            task_store=task_store,
            planning_client=planning_client,
            evidence_assembler=evidence_assembler,
            answer_composer=answer_composer,
            answer_validator=answer_validator,
        )

    service = KnowledgeChatService(orchestrator_factory=orchestrator_factory)
    request.app.state.knowledge_chat_service = service
    return service


async def get_task_result_or_404(task_id: str, store: RedisTaskStore) -> AnalysisResult:
    result = await store.get_result(task_id)
    if result is not None:
        return result

    status_payload = await store.get_status(task_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    raise HTTPException(status_code=404, detail="Task artifact not found.")


def build_artifact_response(result: AnalysisResult, artifact_kind: str) -> FileResponse:
    try:
        path_field, media_type, filename = _ARTIFACT_SPECS[artifact_kind]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task artifact not found.") from exc

    artifact_path = Path(getattr(result, path_field))
    if not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Task artifact not found.")

    return FileResponse(path=artifact_path, media_type=media_type, filename=filename)


async def check_rate_limit(request: Request, store: RedisTaskStore, settings: Settings) -> dict[str, int | bool]:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else None
    if not client_ip:
        client = getattr(request, "client", None)
        client_ip = getattr(client, "host", "unknown")
    return await store.hit_rate_limit(
        f"analyze:{client_ip}",
        limit=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )


async def enqueue_analysis(
    *,
    store: RedisTaskStore,
    queue,
    task_id: str,
    github_url: str,
    task_token: str,
) -> str:
    await store.set_status(TaskStatus(task_id=task_id, state=TaskState.QUEUED))
    await store.set_task_access_token(task_id, task_token)
    await store.set_task_request(task_id, {"github_url": github_url})
    await store.append_event(
        task_id,
        {
            "state": TaskState.QUEUED.value,
            "progress": 0,
        },
    )
    try:
        await queue.enqueue_job("run_analysis_job", task_id, github_url)
    except Exception as exc:
        await store.delete_task(task_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue analysis job.",
        ) from exc
    return task_id


@router.post("/analyze", status_code=202)
async def analyze(
    request: AnalyzeRequest,
    raw_request: Request,
    response: Response,
    task_store: RedisTaskStore = Depends(get_task_store),
    queue=Depends(get_job_queue),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    await require_api_key_scopes(raw_request, settings, required_scopes=("analyze:create",), store=task_store)
    rate_limit = await check_rate_limit(raw_request, task_store, settings)
    response.headers["X-RateLimit-Limit"] = str(rate_limit["limit"])
    response.headers["X-RateLimit-Remaining"] = str(rate_limit["remaining"])
    if not rate_limit["allowed"]:
        await task_store.increment_metric("analyze_rate_limited_total")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded.",
            headers={
                "Retry-After": str(rate_limit["retry_after"]),
                "X-RateLimit-Limit": str(rate_limit["limit"]),
                "X-RateLimit-Remaining": str(rate_limit["remaining"]),
            },
        )

    task_id = uuid4().hex
    task_token = secrets.token_urlsafe(24)
    try:
        github_url = normalize_github_url(str(request.github_url), allowed_hosts=settings.allowed_github_hosts)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    await task_store.increment_metric("analyze_requests_total")
    await enqueue_analysis(
        store=task_store,
        queue=queue,
        task_id=task_id,
        github_url=github_url,
        task_token=task_token,
    )
    await emit_audit_event(
        raw_request,
        action="analyze_submit",
        outcome="accepted",
        task_id=task_id,
        github_url=github_url,
        store=task_store,
    )
    return {
        "task_id": task_id,
        "status_url": f"/api/v1/tasks/{task_id}",
        "result_url": f"/api/v1/tasks/{task_id}/result",
        "stream_url": f"/api/v1/tasks/{task_id}/stream",
        "task_token": task_token,
    }


@router.get("/tasks", response_model=TaskListPage)
async def list_tasks(
    request: Request,
    limit: int = 25,
    offset: int = 0,
    state: TaskState | None = None,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> TaskListPage:
    await require_api_key_scopes(request, settings, required_scopes=("tasks:read",), store=store)
    bounded_limit = min(max(limit, 1), 200)
    bounded_offset = max(offset, 0)
    return await store.list_tasks(limit=bounded_limit, offset=bounded_offset, state=state)


@router.get("/tasks/{task_id}", response_model=TaskStatus)
async def task_status(
    task_id: str,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> TaskStatus:
    await require_task_access(request, task_id, settings, store)
    status = await store.get_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return status


@router.get("/tasks/{task_id}/result", response_model=AnalysisResult)
async def task_result(
    task_id: str,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> AnalysisResult | JSONResponse:
    await require_task_access(request, task_id, settings, store)
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


@router.get("/tasks/{task_id}/artifacts/{artifact_kind}")
async def task_artifact(
    task_id: str,
    artifact_kind: str,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    await require_task_access(request, task_id, settings, store)
    result = await get_task_result_or_404(task_id, store)
    await emit_audit_event(
        request,
        action="task_artifact_download",
        outcome="success",
        task_id=task_id,
        artifact_kind=artifact_kind,
        store=store,
    )
    return build_artifact_response(result, artifact_kind)


async def _request_task_stop(
    task_id: str,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> TaskStatus:
    await require_task_access_scopes(request, task_id, settings, store, required_scopes=("tasks:write",))
    status_payload = await store.get_status(task_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    await store.request_task_cancel(task_id)
    if status_payload.state is TaskState.QUEUED:
        cancelled = TaskStatus(
            task_id=task_id,
            state=TaskState.CANCELLED,
            stage=status_payload.stage,
            progress=status_payload.progress,
            message="Cancellation requested.",
            created_at=status_payload.created_at,
        )
        await store.set_status(cancelled)
        await store.append_event(
            task_id,
            {
                "state": TaskState.CANCELLED.value,
                "stage": cancelled.stage.value if cancelled.stage is not None else None,
                "progress": cancelled.progress,
                "message": "Cancellation requested.",
            },
        )
        return cancelled

    if status_payload.state in _TERMINAL_STATES:
        return status_payload

    updated = TaskStatus(
        task_id=task_id,
        state=status_payload.state,
        stage=status_payload.stage,
        progress=status_payload.progress,
        message="Cancellation requested.",
        error=status_payload.error,
        created_at=status_payload.created_at,
    )
    await store.set_status(updated)
    await store.append_event(
        task_id,
        {
            "state": updated.state.value,
            "stage": updated.stage.value if updated.stage is not None else None,
            "progress": updated.progress,
            "message": "Cancellation requested.",
        },
    )
    return updated


@router.post("/tasks/{task_id}/stop", response_model=TaskStatus, status_code=202)
async def stop_task(
    task_id: str,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> TaskStatus:
    return await _request_task_stop(task_id, request, store, settings)


@router.post("/tasks/{task_id}/cancel", response_model=TaskStatus, status_code=202)
async def cancel_task(
    task_id: str,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> TaskStatus:
    return await _request_task_stop(task_id, request, store, settings)


@router.post("/tasks/{task_id}/retry", status_code=202)
async def retry_task(
    task_id: str,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    queue=Depends(get_job_queue),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    await require_task_access_scopes(request, task_id, settings, store, required_scopes=("tasks:write",))
    status_payload = await store.get_status(task_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if status_payload.state not in {TaskState.FAILED, TaskState.CANCELLED}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled tasks can be retried.")

    task_request = await store.get_task_request(task_id)
    github_url = task_request.get("github_url") if task_request is not None else None
    if not isinstance(github_url, str) or not github_url:
        raise HTTPException(status_code=404, detail="Original task request was not found.")

    retry_task_id = uuid4().hex
    retry_task_token = secrets.token_urlsafe(24)
    await enqueue_analysis(
        store=store,
        queue=queue,
        task_id=retry_task_id,
        github_url=github_url,
        task_token=retry_task_token,
    )
    return {
        "task_id": retry_task_id,
        "status_url": f"/api/v1/tasks/{retry_task_id}",
        "result_url": f"/api/v1/tasks/{retry_task_id}/result",
        "stream_url": f"/api/v1/tasks/{retry_task_id}/stream",
        "task_token": retry_task_token,
    }

@router.get("/tasks/{task_id}/stream")
async def task_stream(
    task_id: str,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    await require_task_access(request, task_id, settings, store)
    initial_status = await store.get_status(task_id)
    if initial_status is None:
        raise HTTPException(status_code=404, detail="Task not found.")

    async def event_stream():
        next_index = 0
        while True:
            events = await store.get_events_since(task_id, next_index)
            for event in events:
                next_index += 1
                yield f"data: {json.dumps(event, separators=(',', ':'))}\n\n"

            status_payload = await store.get_status(task_id)
            if status_payload is None:
                break
            if status_payload.state in _TERMINAL_STATES:
                break
            await asyncio.sleep(settings.stream_poll_interval_seconds)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/tasks/{task_id}/chat/messages", response_model=TaskChatHistory)
async def task_chat_messages(
    task_id: str,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
) -> TaskChatHistory:
    await require_task_access(request, task_id, settings, store)
    status_payload = await store.get_status(task_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskChatHistory(task_id=task_id, messages=await store.get_chat_messages(task_id))


@router.post("/tasks/{task_id}/chat", response_model=TaskChatExchange)
async def task_chat(
    task_id: str,
    payload: TaskChatRequest,
    request: Request,
    store: RedisTaskStore = Depends(get_task_store),
    settings: Settings = Depends(get_settings),
    chat_service: KnowledgeChatService = Depends(get_knowledge_chat_service),
) -> TaskChatExchange:
    await require_task_access_scopes(request, task_id, settings, store, required_scopes=("tasks:write",))
    status_payload = await store.get_status(task_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if status_payload.state is not TaskState.SUCCEEDED or status_payload.knowledge_state is not TaskKnowledgeState.READY:
        raise HTTPException(status_code=409, detail="Task chat is available only after the knowledge base is ready.")

    result = await store.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task result not found.")
    artifacts = ArtifactPaths(base_dir=settings.artifacts_dir, task_id=task_id)
    db_path = artifacts.knowledge_db_path
    if not db_path.is_file():
        raise HTTPException(status_code=404, detail="Task knowledge base not found.")
    repo_map_path = artifacts.repo_map_path if artifacts.repo_map_path.is_file() else None

    history = await store.get_chat_messages(task_id)
    user_message = TaskChatMessage(
        message_id=uuid4().hex,
        role="user",
        content=payload.question.strip(),
    )
    await store.append_chat_message(task_id, user_message)

    answer = await chat_service.answer_question(
        task_id=task_id,
        db_path=db_path,
        repo_map_path=repo_map_path,
        question=user_message.content,
        history=history,
    )
    assistant_message = TaskChatMessage(
        message_id=uuid4().hex,
        role="assistant",
        content=answer.answer,
        citations=answer.citations,
        graph_evidence=answer.graph_evidence,
        supplemental_notes=answer.supplemental_notes,
        confidence=answer.confidence,
        answer_source=answer.answer_source,
        planner_metadata=answer.planner_metadata,
    )
    await store.append_chat_message(task_id, assistant_message)
    return TaskChatExchange(
        task_id=task_id,
        user_message=user_message,
        assistant_message=assistant_message,
    )
