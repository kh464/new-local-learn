from __future__ import annotations

import asyncio
import inspect
import json
import logging
from pathlib import Path

from app.core.models import (
    AnalysisResult,
    AgentExecutionNode,
    AgentMetadata,
    BackendSummary,
    CritiqueSummary,
    DetectedStackSummary,
    DeploySummary,
    FrontendSummary,
    LogicSummary,
    MermaidSections,
    RepositorySummary,
    TaskKnowledgeState,
    TaskStage,
    TaskState,
    TaskStatus,
    TutorialSummary,
)
from app.services.analyzers.backend_analyzer import BackendAnalyzer
from app.services.analyzers.critique_builder import CritiqueBuilder
from app.services.analyzers.deploy_analyzer import DeployAnalyzer
from app.services.analyzers.frontend_analyzer import FrontendAnalyzer
from app.services.analyzers.logic_mapper import LogicMapper
from app.services.analyzers.stack_detector import StackDetector
from app.services.analyzers.tutor_composer import TutorComposer
from app.services.docs.html_compiler import HtmlCompiler
from app.services.docs.markdown_compiler import MarkdownCompiler
from app.services.docs.mermaid_builder import MermaidBuilder
from app.services.docs.pdf_compiler import PdfCompiler
from app.services.knowledge.index_builder import KnowledgeIndexBuilder
from app.services.knowledge.repo_map_builder import RepoMapBuilder
from app.services.repo.fetcher import normalize_github_url
from app.services.repo.scanner import RepositoryScanner
from app.storage.artifacts import ArtifactPaths
from app.storage.artifacts import prune_expired_task_artifacts
from app.storage.task_store import RedisTaskStore

_TASK_LOGGER = logging.getLogger("app.tasks")
_RUNNING_STAGE_PROGRESS = {
    TaskStage.FETCH_REPO: 5,
    TaskStage.SCAN_TREE: 20,
    TaskStage.DETECT_STACK: 35,
    TaskStage.ANALYZE_BACKEND: 50,
    TaskStage.ANALYZE_FRONTEND: 65,
    TaskStage.BUILD_DOC: 85,
    TaskStage.BUILD_KNOWLEDGE: 95,
}


class TaskCancelledError(RuntimeError):
    pass


class ExecutionTracker:
    def __init__(self, nodes: list[AgentExecutionNode], *, used_roles: list[str]) -> None:
        self._nodes = {
            node.node: node.model_copy(deep=True)
            for node in nodes
        }
        self._used_roles = used_roles
        self._fallbacks: list[str] = []

    def mark_started(self, node_name: str) -> None:
        self._update(node_name, status="running")

    def mark_completed(self, node_name: str, *, execution_mode: str | None = None, reason: str | None = None) -> None:
        self._update(node_name, status="completed", execution_mode=execution_mode, reason=reason)

    def mark_failed(self, node_name: str, *, reason: str) -> None:
        self._update(node_name, status="failed", reason=reason)

    def mark_fallback(self, node_name: str, *, reason: str) -> None:
        self._update(node_name, status="fallback", execution_mode="fallback", reason=reason)
        if node_name not in self._fallbacks:
            self._fallbacks.append(node_name)

    def build(self) -> AgentMetadata:
        return AgentMetadata(
            enabled=True,
            used_roles=list(self._used_roles),
            fallbacks=list(self._fallbacks),
            execution_nodes=[self._nodes[name] for name in self._nodes],
        )

    def running_nodes(self) -> list[str]:
        return [name for name, node in self._nodes.items() if node.status == "running"]

    def _update(
        self,
        node_name: str,
        *,
        status: str,
        execution_mode: str | None = None,
        reason: str | None = None,
    ) -> None:
        node = self._nodes[node_name]
        node.status = status
        if execution_mode is not None:
            node.execution_mode = execution_mode
        if reason is not None:
            node.reason = reason


def _build_execution_tracker(*, tutorial_generator_present: bool) -> ExecutionTracker:
    nodes = [
        AgentExecutionNode(
            node="stack_detection",
            stage=TaskStage.DETECT_STACK.value,
            kind="analysis",
            status="pending",
            depends_on=[],
            execution_mode="deterministic",
        ),
        AgentExecutionNode(
            node="backend_analysis",
            stage=TaskStage.ANALYZE_BACKEND.value,
            kind="analysis",
            status="pending",
            depends_on=["stack_detection"],
            execution_mode="deterministic",
        ),
        AgentExecutionNode(
            node="frontend_analysis",
            stage=TaskStage.ANALYZE_FRONTEND.value,
            kind="analysis",
            status="pending",
            depends_on=["stack_detection"],
            execution_mode="deterministic",
        ),
        AgentExecutionNode(
            node="deploy_analysis",
            stage=TaskStage.ANALYZE_FRONTEND.value,
            kind="analysis",
            status="pending",
            depends_on=["stack_detection"],
            execution_mode="deterministic",
        ),
        AgentExecutionNode(
            node="logic_mapping",
            stage=TaskStage.BUILD_DOC.value,
            kind="analysis",
            status="pending",
            depends_on=["backend_analysis", "frontend_analysis"],
            execution_mode="deterministic",
        ),
        AgentExecutionNode(
            node="critic_review",
            stage=TaskStage.BUILD_DOC.value,
            kind="analysis",
            status="pending",
            depends_on=["backend_analysis", "frontend_analysis", "deploy_analysis"],
            execution_mode="deterministic",
        ),
        AgentExecutionNode(
            node="tutorial_generation",
            stage=TaskStage.BUILD_DOC.value,
            kind="llm" if tutorial_generator_present else "analysis",
            status="pending",
            depends_on=["logic_mapping"],
            execution_mode="llm" if tutorial_generator_present else "deterministic",
        ),
    ]
    used_roles = [
        "stack-detector",
        "backend-analyzer",
        "frontend-analyzer",
        "deploy-analyzer",
        "logic-mapper",
        "critic",
        "tutor",
    ]
    return ExecutionTracker(nodes, used_roles=used_roles)


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


def _get_ctx_value(ctx, name: str):
    if isinstance(ctx, dict):
        return ctx.get(name)
    return getattr(ctx, name, None)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


async def _build_tutorial_summary(
    ctx,
    *,
    store: RedisTaskStore,
    tracker: ExecutionTracker,
    repo_summary: dict[str, object],
    detected_stack: dict[str, object],
    backend_summary: dict[str, object],
    frontend_summary: dict[str, object],
    logic_summary: dict[str, object],
    file_contents: dict[str, str],
) -> dict[str, object]:
    tutorial_generator = _get_ctx_value(ctx, "tutorial_generator")
    if tutorial_generator is None:
        tracker.mark_started("tutorial_generation")
        tracker.mark_completed("tutorial_generation", execution_mode="deterministic")
        return TutorComposer().compose(detected_stack, logic_summary)

    tracker.mark_started("tutorial_generation")
    await store.increment_metric("analysis_llm_requests_total")
    try:
        tutorial_summary = await _maybe_await(
            tutorial_generator(
                repo_summary=repo_summary,
                detected_stack=detected_stack,
                backend_summary=backend_summary,
                frontend_summary=frontend_summary,
                logic_summary=logic_summary,
                file_contents=file_contents,
            )
        )
        await store.increment_metric("analysis_llm_success_total")
        tracker.mark_completed("tutorial_generation", execution_mode="llm")
        return TutorialSummary.model_validate(tutorial_summary).model_dump()
    except Exception as exc:
        await store.increment_metric("analysis_llm_failures_total")
        tracker.mark_fallback("tutorial_generation", reason=str(exc))
        _TASK_LOGGER.warning(
            json.dumps(
                {
                    "message": "llm_tutorial_fallback",
                    "error": str(exc),
                },
                separators=(",", ":"),
            )
        )
        return TutorComposer().compose(detected_stack, logic_summary)


async def _run_sync_execution_node(
    tracker: ExecutionTracker,
    node_name: str,
    func,
    *args,
    **kwargs,
) -> object:
    tracker.mark_started(node_name)
    try:
        result = await asyncio.to_thread(func, *args, **kwargs)
    except Exception as exc:
        tracker.mark_failed(node_name, reason=str(exc))
        raise
    tracker.mark_completed(node_name)
    return result


async def _set_stage(
    store: RedisTaskStore,
    *,
    task_id: str,
    state: TaskState,
    stage: TaskStage,
    progress: int,
    created_at,
    error: str | None = None,
    knowledge_state: TaskKnowledgeState | None = None,
    knowledge_error: str | None = None,
) -> None:
    status = TaskStatus(
        task_id=task_id,
        state=state,
        stage=stage,
        progress=progress,
        error=error,
        knowledge_state=knowledge_state or TaskKnowledgeState.PENDING,
        knowledge_error=knowledge_error,
        created_at=created_at,
    )
    await store.set_status(status)
    event = {
        "state": state.value,
        "stage": stage.value,
        "progress": progress,
    }
    if error is not None:
        event["error"] = error
    if knowledge_state is not None and knowledge_state is not TaskKnowledgeState.PENDING:
        event["knowledge_state"] = knowledge_state.value
    if knowledge_error is not None:
        event["knowledge_error"] = knowledge_error
    await store.append_event(task_id, event)
    log_payload = {
        "task_id": task_id,
        "state": state.value,
        "stage": stage.value,
        "progress": progress,
    }
    if error is not None:
        log_payload["error"] = error
    if knowledge_state is not None and knowledge_state is not TaskKnowledgeState.PENDING:
        log_payload["knowledge_state"] = knowledge_state.value
    if knowledge_error is not None:
        log_payload["knowledge_error"] = knowledge_error
    _TASK_LOGGER.info(json.dumps(log_payload, separators=(",", ":")))


async def _ensure_not_cancelled(
    store: RedisTaskStore,
    *,
    task_id: str,
    created_at,
    progress: int,
    stage: TaskStage,
) -> None:
    if not await store.is_task_cancel_requested(task_id):
        return

    cancelled = TaskStatus(
        task_id=task_id,
        state=TaskState.CANCELLED,
        stage=stage,
        progress=progress,
        message="Cancellation requested.",
        created_at=created_at,
    )
    await store.set_status(cancelled)
    await store.append_event(
        task_id,
        {
            "state": TaskState.CANCELLED.value,
            "stage": stage.value,
            "progress": progress,
            "message": "Cancellation requested.",
        },
    )
    raise TaskCancelledError(f"Task {task_id} was cancelled during {stage.value}.")


async def run_analysis_job(ctx, task_id: str, github_url: str) -> dict[str, object]:
    store = _get_task_store(ctx)
    tracker = _build_execution_tracker(tutorial_generator_present=_get_ctx_value(ctx, "tutorial_generator") is not None)
    running_status = TaskStatus(task_id=task_id, state=TaskState.RUNNING, stage=TaskStage.FETCH_REPO, progress=5)
    await _set_stage(
        store,
        task_id=task_id,
        state=TaskState.RUNNING,
        stage=TaskStage.FETCH_REPO,
        progress=_RUNNING_STAGE_PROGRESS[TaskStage.FETCH_REPO],
        created_at=running_status.created_at,
    )
    try:
        await _ensure_not_cancelled(
            store,
            task_id=task_id,
            created_at=running_status.created_at,
            progress=0,
            stage=TaskStage.FETCH_REPO,
        )
        settings = _get_ctx_value(ctx, "settings")
        if settings is None:
            raise RuntimeError("Settings are not available in job context.")
        clone_repo = _get_ctx_value(ctx, "clone_repo")
        if clone_repo is None:
            raise RuntimeError("clone_repo is not available in job context.")
        read_files = _get_ctx_value(ctx, "read_files")
        if read_files is None:
            raise RuntimeError("read_files is not available in job context.")

        allowed_github_hosts = getattr(settings, "allowed_github_hosts", ("github.com", "www.github.com"))
        normalized_url = normalize_github_url(github_url, allowed_hosts=allowed_github_hosts)
        artifacts = ArtifactPaths(base_dir=Path(settings.artifacts_dir), task_id=task_id)
        removed_artifacts = prune_expired_task_artifacts(artifacts.base_dir, getattr(settings, "artifact_ttl_seconds", 0))
        if removed_artifacts:
            _TASK_LOGGER.info(
                json.dumps(
                    {"message": "artifact_cleanup", "removed": removed_artifacts},
                    separators=(",", ":"),
                )
            )
        artifacts.task_dir.mkdir(parents=True, exist_ok=True)

        repo_path = Path(await _maybe_await(clone_repo(normalized_url, artifacts.repo_dir)))
        await _ensure_not_cancelled(
            store,
            task_id=task_id,
            created_at=running_status.created_at,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.FETCH_REPO],
            stage=TaskStage.FETCH_REPO,
        )
        await _set_stage(
            store,
            task_id=task_id,
            state=TaskState.RUNNING,
            stage=TaskStage.SCAN_TREE,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.SCAN_TREE],
            created_at=running_status.created_at,
        )
        scanner = RepositoryScanner(
            max_file_count=settings.max_file_count,
            max_file_bytes=settings.max_file_bytes,
            max_total_bytes=settings.max_total_bytes,
        )
        repo_summary = scanner.scan(repo_path)
        file_contents = await _maybe_await(read_files(repo_path, repo_summary["files"]))
        await _ensure_not_cancelled(
            store,
            task_id=task_id,
            created_at=running_status.created_at,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.SCAN_TREE],
            stage=TaskStage.SCAN_TREE,
        )

        await _set_stage(
            store,
            task_id=task_id,
            state=TaskState.RUNNING,
            stage=TaskStage.DETECT_STACK,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.DETECT_STACK],
            created_at=running_status.created_at,
        )
        tracker.mark_started("stack_detection")
        detected_stack = StackDetector().detect(repo_summary["files"], file_contents)
        tracker.mark_completed("stack_detection")
        await _ensure_not_cancelled(
            store,
            task_id=task_id,
            created_at=running_status.created_at,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.DETECT_STACK],
            stage=TaskStage.DETECT_STACK,
        )

        await _set_stage(
            store,
            task_id=task_id,
            state=TaskState.RUNNING,
            stage=TaskStage.ANALYZE_BACKEND,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.ANALYZE_BACKEND],
            created_at=running_status.created_at,
        )
        await _set_stage(
            store,
            task_id=task_id,
            state=TaskState.RUNNING,
            stage=TaskStage.ANALYZE_FRONTEND,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.ANALYZE_FRONTEND],
            created_at=running_status.created_at,
        )
        backend_summary, frontend_summary, deploy_summary = await asyncio.gather(
            _run_sync_execution_node(tracker, "backend_analysis", BackendAnalyzer().analyze, file_contents),
            _run_sync_execution_node(tracker, "frontend_analysis", FrontendAnalyzer().analyze, file_contents),
            _run_sync_execution_node(tracker, "deploy_analysis", DeployAnalyzer().analyze, repo_summary["files"], file_contents),
        )
        await _ensure_not_cancelled(
            store,
            task_id=task_id,
            created_at=running_status.created_at,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.ANALYZE_FRONTEND],
            stage=TaskStage.ANALYZE_FRONTEND,
        )
        repo_overview = RepositorySummary(
            name=normalized_url.rstrip("/").split("/")[-1],
            files=repo_summary["files"],
            key_files=repo_summary["key_files"],
            file_count=repo_summary["file_count"],
        )
        logic_summary, critique_summary = await asyncio.gather(
            _run_sync_execution_node(tracker, "logic_mapping", LogicMapper().map_flows, frontend_summary, backend_summary),
            _run_sync_execution_node(
                tracker,
                "critic_review",
                CritiqueBuilder().build,
                repo_summary=repo_overview.model_dump(),
                backend_summary=backend_summary,
                frontend_summary=frontend_summary,
                deploy_summary=deploy_summary,
            ),
        )
        tutorial_summary = await _build_tutorial_summary(
            ctx,
            store=store,
            tracker=tracker,
            repo_summary=repo_overview.model_dump(),
            detected_stack=detected_stack,
            backend_summary=backend_summary,
            frontend_summary=frontend_summary,
            logic_summary=logic_summary,
            file_contents=file_contents,
        )
        await _ensure_not_cancelled(
            store,
            task_id=task_id,
            created_at=running_status.created_at,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.BUILD_DOC],
            stage=TaskStage.BUILD_DOC,
        )
        mermaid_sections = {"system": MermaidBuilder().build_system_diagram(detected_stack)}

        await _set_stage(
            store,
            task_id=task_id,
            state=TaskState.RUNNING,
            stage=TaskStage.BUILD_DOC,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.BUILD_DOC],
            created_at=running_status.created_at,
        )
        markdown = MarkdownCompiler().compile(
            task_id=task_id,
            repo_summary=repo_overview.model_dump(),
            detected_stack=detected_stack,
            backend_summary=backend_summary,
            frontend_summary=frontend_summary,
            logic_summary=logic_summary,
            tutorial_summary=tutorial_summary,
            deploy_summary=deploy_summary,
            critique_summary=critique_summary,
            mermaid_sections=mermaid_sections,
        )

        artifacts.markdown_path.write_text(markdown, encoding="utf-8")
        html_output = HtmlCompiler().compile(title=f"Analysis Report: {repo_overview.name}", markdown=markdown)
        artifacts.html_path.write_text(html_output, encoding="utf-8")
        pdf_output = PdfCompiler().compile(title=f"Analysis Report: {repo_overview.name}", markdown=markdown)
        artifacts.pdf_path.write_bytes(pdf_output)
        result = AnalysisResult(
            github_url=normalized_url,
            repo_path=str(repo_path),
            markdown_path=str(artifacts.markdown_path),
            html_path=str(artifacts.html_path),
            pdf_path=str(artifacts.pdf_path),
            repo_summary=repo_overview,
            detected_stack=DetectedStackSummary.model_validate(detected_stack),
            backend_summary=BackendSummary.model_validate(backend_summary),
            frontend_summary=FrontendSummary.model_validate(frontend_summary),
            deploy_summary=DeploySummary.model_validate(deploy_summary),
            logic_summary=LogicSummary.model_validate(logic_summary),
            tutorial_summary=TutorialSummary.model_validate(tutorial_summary),
            critique_summary=CritiqueSummary.model_validate(critique_summary),
            mermaid_sections=MermaidSections.model_validate(mermaid_sections),
            agent_metadata=tracker.build(),
        )
        await store.set_result(task_id, result.model_dump())
        knowledge_builder = _get_ctx_value(ctx, "knowledge_builder")
        if knowledge_builder is None:
            knowledge_builder = KnowledgeIndexBuilder(max_file_bytes=settings.max_file_bytes)
        code_graph_builder = _get_ctx_value(ctx, "code_graph_builder")
        summary_generation_builder = _get_ctx_value(ctx, "summary_generation_builder")
        embedding_index_builder = _get_ctx_value(ctx, "embedding_index_builder")
        repo_map_builder = _get_ctx_value(ctx, "repo_map_builder")
        if repo_map_builder is None:
            repo_map_builder = RepoMapBuilder()
        knowledge_state = TaskKnowledgeState.READY
        knowledge_error = None
        await _set_stage(
            store,
            task_id=task_id,
            state=TaskState.RUNNING,
            stage=TaskStage.BUILD_KNOWLEDGE,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.BUILD_KNOWLEDGE],
            created_at=running_status.created_at,
            knowledge_state=TaskKnowledgeState.RUNNING,
        )
        await _ensure_not_cancelled(
            store,
            task_id=task_id,
            created_at=running_status.created_at,
            progress=_RUNNING_STAGE_PROGRESS[TaskStage.BUILD_KNOWLEDGE],
            stage=TaskStage.BUILD_KNOWLEDGE,
        )
        try:
            await asyncio.to_thread(
                knowledge_builder.build,
                task_id=task_id,
                repo_path=repo_path,
                db_path=artifacts.knowledge_db_path,
            )
        except Exception as exc:
            knowledge_state = TaskKnowledgeState.FAILED
            knowledge_error = str(exc)
            _TASK_LOGGER.warning(
                json.dumps(
                    {
                        "message": "knowledge_build_failed",
                        "task_id": task_id,
                        "error": knowledge_error,
                    },
                    separators=(",", ":"),
                )
            )
        if knowledge_state is TaskKnowledgeState.READY:
            if code_graph_builder is not None:
                try:
                    await asyncio.to_thread(
                        code_graph_builder.build,
                        task_id=task_id,
                        repo_root=repo_path,
                        db_path=artifacts.knowledge_db_path,
                    )
                except Exception as exc:
                    _TASK_LOGGER.warning(
                        json.dumps(
                            {
                                "message": "code_graph_build_failed",
                                "task_id": task_id,
                                "error": str(exc),
                            },
                            separators=(",", ":"),
                        )
                    )
            if summary_generation_builder is not None:
                try:
                    summary_build_result = summary_generation_builder.build(
                        task_id=task_id,
                        db_path=artifacts.knowledge_db_path,
                        repo_root=repo_path,
                    )
                    if inspect.isawaitable(summary_build_result):
                        await summary_build_result
                except Exception as exc:
                    _TASK_LOGGER.warning(
                        json.dumps(
                            {
                                "message": "summary_generation_build_failed",
                                "task_id": task_id,
                                "error": str(exc),
                            },
                            separators=(",", ":"),
                        )
                    )
            if embedding_index_builder is not None:
                try:
                    embedding_build_result = embedding_index_builder.build(
                        task_id=task_id,
                        db_path=artifacts.knowledge_db_path,
                    )
                    if inspect.isawaitable(embedding_build_result):
                        await embedding_build_result
                except Exception as exc:
                    _TASK_LOGGER.warning(
                        json.dumps(
                            {
                                "message": "embedding_index_build_failed",
                                "task_id": task_id,
                                "error": str(exc),
                            },
                            separators=(",", ":"),
                        )
                    )
            try:
                await asyncio.to_thread(
                    repo_map_builder.build,
                    task_id=task_id,
                    repo_path=repo_path,
                    output_path=artifacts.repo_map_path,
                )
            except Exception as exc:
                _TASK_LOGGER.warning(
                    json.dumps(
                        {
                            "message": "repo_map_build_failed",
                            "task_id": task_id,
                            "error": str(exc),
                        },
                        separators=(",", ":"),
                    )
                )
        await store.increment_metric("analysis_jobs_succeeded_total")
        await _set_stage(
            store,
            task_id=task_id,
            state=TaskState.SUCCEEDED,
            stage=TaskStage.FINALIZE,
            progress=100,
            created_at=running_status.created_at,
            knowledge_state=knowledge_state,
            knowledge_error=knowledge_error,
        )
        return {"task_id": task_id, "state": TaskState.SUCCEEDED.value, "result": result.model_dump()}
    except TaskCancelledError:
        return {"task_id": task_id, "state": TaskState.CANCELLED.value}
    except Exception as exc:
        for node_name in tracker.running_nodes():
            tracker.mark_failed(node_name, reason=str(exc))
        await store.increment_metric("analysis_jobs_failed_total")
        await _set_stage(
            store,
            task_id=task_id,
            state=TaskState.FAILED,
            stage=TaskStage.FINALIZE,
            progress=100,
            created_at=running_status.created_at,
            error=str(exc),
        )
        return {"task_id": task_id, "state": TaskState.FAILED.value}
