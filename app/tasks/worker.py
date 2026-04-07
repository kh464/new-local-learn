import logging

from arq.connections import RedisSettings

from app.core.config import Settings
from app.services.llm.client import ChatCompletionClient
from app.services.llm.config import load_runtime_config
from app.services.llm.report_enhancer import TutorialLLMEnhancer
from app.services.repo.fetcher import clone_github_repo, read_repository_files
from app.storage.task_store import RedisTaskStore
from app.tasks.jobs import run_analysis_job

settings = Settings()
_WORKER_LOGGER = logging.getLogger("app.worker")


async def startup(ctx: dict) -> None:
    ctx["settings"] = settings
    ctx["task_store"] = RedisTaskStore(ctx["redis"], ttl_seconds=getattr(settings, "task_ttl_seconds", None))
    
    async def clone_repo_with_settings(github_url: str, destination):
        return await clone_github_repo(github_url, destination, timeout_seconds=settings.clone_timeout_seconds)

    ctx["clone_repo"] = clone_repo_with_settings
    ctx["read_files"] = read_repository_files
    tutorial_generator = _build_tutorial_generator()
    if tutorial_generator is not None:
        ctx["tutorial_generator"] = tutorial_generator


def _build_tutorial_generator():
    if not settings.llm_enabled:
        return None
    if not settings.llm_config_path.is_file():
        return None
    try:
        runtime_config = load_runtime_config(settings.llm_config_path, settings.llm_profile)
    except Exception as exc:
        _WORKER_LOGGER.warning("Failed to load LLM config: %s", exc)
        return None

    enhancer = TutorialLLMEnhancer(
        ChatCompletionClient(runtime_config),
        max_prompt_chars=settings.llm_max_prompt_chars,
        max_snippet_chars=settings.llm_max_snippet_chars,
    )
    return enhancer.generate_tutorial


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [run_analysis_job]
    on_startup = startup
    job_timeout = settings.worker_job_timeout_seconds
    max_jobs = settings.worker_max_jobs
