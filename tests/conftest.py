from __future__ import annotations

import inspect
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from app.main import create_app
from app.storage.task_store import RedisTaskStore


@pytest.fixture
def tmp_path() -> Path:
    base = Path.cwd() / "tmpbase"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir()
    return path


@pytest_asyncio.fixture
async def fakeredis_client():
    client = FakeRedis()
    try:
        yield client
    finally:
        result = client.aclose()
        if inspect.isawaitable(result):
            await result


@pytest_asyncio.fixture
async def fake_job_context(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    return {"redis": fakeredis_client, "task_store": store}


@pytest_asyncio.fixture
async def api_client(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    app = create_app(task_store=store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
