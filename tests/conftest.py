from __future__ import annotations

import inspect
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

try:
    from fakeredis.aioredis import FakeRedis
except ImportError:  # pragma: no cover
    FakeRedis = None

from app.main import create_app


@pytest.fixture
def tmp_path() -> Path:
    base = Path.cwd() / "tmpbase"
    base.mkdir(parents=True, exist_ok=True)
    path = base / uuid4().hex
    path.mkdir()
    return path


@pytest_asyncio.fixture
async def fakeredis_client():
    if FakeRedis is None:
        client = _MemoryRedis()
    else:
        client = FakeRedis()
    try:
        yield client
    finally:
        result = client.close()
        if inspect.isawaitable(result):
            await result


@pytest_asyncio.fixture
async def api_client():
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class _MemoryRedis:
    def __init__(self) -> None:
        self._values: dict[str, str | bytes] = {}
        self._lists: dict[str, list[str | bytes]] = {}

    async def get(self, key: str):
        return self._values.get(key)

    async def set(self, key: str, value):
        self._values[key] = value
        return True

    async def rpush(self, key: str, value):
        items = self._lists.setdefault(key, [])
        items.append(value)
        return len(items)

    async def lrange(self, key: str, start: int, end: int):
        items = self._lists.get(key, [])
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    def close(self):
        return None
