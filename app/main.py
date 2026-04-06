from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.routes.tasks import router as tasks_router
from app.core.config import Settings
from app.storage.task_store import RedisTaskStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if getattr(app.state, "task_store", None) is not None:
        yield
        return

    settings = Settings()
    try:
        from redis.asyncio import from_url
    except ImportError as exc:  # pragma: no cover - dependency required in prod
        raise RuntimeError("Redis dependency is required for task storage.") from exc

    client = from_url(settings.redis_url)
    app.state.redis_client = client
    app.state.task_store = RedisTaskStore(client)
    try:
        yield
    finally:
        close_result = client.close()
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
