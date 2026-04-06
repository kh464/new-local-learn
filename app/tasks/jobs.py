from __future__ import annotations

import inspect
from pathlib import Path

from app.core.models import AnalysisResult, TaskStage, TaskState, TaskStatus
from app.services.analyzers.backend_analyzer import BackendAnalyzer
from app.services.analyzers.frontend_analyzer import FrontendAnalyzer
from app.services.analyzers.logic_mapper import LogicMapper
from app.services.analyzers.stack_detector import StackDetector
from app.services.analyzers.tutor_composer import TutorComposer
from app.services.docs.markdown_compiler import MarkdownCompiler
from app.services.docs.mermaid_builder import MermaidBuilder
from app.services.repo.fetcher import normalize_github_url
from app.services.repo.scanner import RepositoryScanner
from app.storage.artifacts import ArtifactPaths
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


def _get_ctx_value(ctx, name: str):
    if isinstance(ctx, dict):
        return ctx.get(name)
    return getattr(ctx, name, None)


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


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
    try:
        settings = _get_ctx_value(ctx, "settings")
        if settings is None:
            raise RuntimeError("Settings are not available in job context.")
        clone_repo = _get_ctx_value(ctx, "clone_repo")
        if clone_repo is None:
            raise RuntimeError("clone_repo is not available in job context.")
        read_files = _get_ctx_value(ctx, "read_files")
        if read_files is None:
            raise RuntimeError("read_files is not available in job context.")

        normalized_url = normalize_github_url(github_url)
        artifacts = ArtifactPaths(base_dir=Path(settings.artifacts_dir), task_id=task_id)
        artifacts.task_dir.mkdir(parents=True, exist_ok=True)

        repo_path = Path(await _maybe_await(clone_repo(normalized_url, artifacts.repo_dir)))
        scanner = RepositoryScanner(
            max_file_count=settings.max_file_count,
            max_file_bytes=settings.max_file_bytes,
        )
        repo_summary = scanner.scan(repo_path)
        file_contents = await _maybe_await(read_files(repo_path, repo_summary["files"]))

        detected_stack = StackDetector().detect(repo_summary["files"], file_contents)
        backend_summary = BackendAnalyzer().analyze(file_contents)
        frontend_summary = FrontendAnalyzer().analyze(file_contents)
        logic_summary = LogicMapper().map_flows(frontend_summary, backend_summary)
        tutorial_summary = TutorComposer().compose(detected_stack, logic_summary)
        mermaid_sections = {"system": MermaidBuilder().build_system_diagram(detected_stack)}
        markdown = MarkdownCompiler().compile(
            task_id=task_id,
            repo_summary={
                "name": normalized_url.rstrip("/").split("/")[-1],
                "key_files": repo_summary["key_files"],
            },
            detected_stack=detected_stack,
            backend_summary=backend_summary,
            frontend_summary=frontend_summary,
            logic_summary=logic_summary,
            tutorial_summary=tutorial_summary,
            mermaid_sections=mermaid_sections,
        )

        artifacts.markdown_path.write_text(markdown, encoding="utf-8")
        result = AnalysisResult(
            github_url=normalized_url,
            repo_path=str(repo_path),
            markdown_path=str(artifacts.markdown_path),
            detected_stack=detected_stack,
        )
        await store.set_result(task_id, result.model_dump())
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
        return {"task_id": task_id, "state": TaskState.SUCCEEDED.value, "result": result.model_dump()}
    except Exception as exc:
        failed_status = TaskStatus(
            task_id=task_id,
            state=TaskState.FAILED,
            stage=TaskStage.FINALIZE,
            progress=100,
            error=str(exc),
            created_at=running_status.created_at,
        )
        await store.set_status(failed_status)
        await store.append_event(
            task_id,
            {
                "state": TaskState.FAILED.value,
                "stage": TaskStage.FINALIZE.value,
                "progress": 100,
                "error": str(exc),
            },
        )
        return {"task_id": task_id, "state": TaskState.FAILED.value}
