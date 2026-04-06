from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.routes.tasks import router as tasks_router
from app.core.config import Settings
from app.storage.task_store import RedisTaskStore


def _create_redis_client(redis_url: str):
    try:
        from redis.asyncio import from_url
    except ImportError as exc:  # pragma: no cover - dependency required in prod
        raise RuntimeError("Redis dependency is required for task storage.") from exc
    return from_url(redis_url)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if getattr(app.state, "task_store", None) is not None:
        yield
        return

    settings = Settings()
    client = _create_redis_client(settings.redis_url)
    app.state.redis_client = client
    app.state.task_store = RedisTaskStore(client)
    try:
        yield
    finally:
        close = getattr(client, "aclose", None) or getattr(client, "close", None)
        if close is not None:
            close_result = close()
            if inspect.isawaitable(close_result):
                await close_result
        disconnect = getattr(client, "connection_pool", None)
        if disconnect is not None:
            disconnect_result = client.connection_pool.disconnect()
            if inspect.isawaitable(disconnect_result):
                await disconnect_result


def create_app(task_store: RedisTaskStore | None = None) -> FastAPI:
    app = FastAPI(title="Github Tech Doc Generator", lifespan=lifespan)
    if task_store is not None:
        app.state.task_store = task_store
    app.include_router(tasks_router, prefix="/api/v1")
    return app


app = create_app()
