from __future__ import annotations

import json
from typing import Any

from app.core.models import TaskStatus


class RedisTaskStore:
    def __init__(self, client, prefix: str = "tasks") -> None:
        self._client = client
        self._prefix = prefix

    def _status_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:status"

    def _result_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:result"

    def _events_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:events"

    async def set_status(self, status: TaskStatus) -> None:
        payload = status.model_dump_json()
        await self._client.set(self._status_key(status.task_id), payload)

    async def get_status(self, task_id: str) -> TaskStatus | None:
        raw = await self._client.get(self._status_key(task_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return TaskStatus.model_validate_json(raw)

    async def set_result(self, task_id: str, result: dict[str, Any]) -> None:
        payload = json.dumps(result, default=str)
        await self._client.set(self._result_key(task_id), payload)

    async def get_result(self, task_id: str) -> dict[str, Any] | None:
        raw = await self._client.get(self._result_key(task_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def append_event(self, task_id: str, event: dict[str, Any]) -> int:
        payload = json.dumps(event, default=str)
        return await self._client.rpush(self._events_key(task_id), payload)

    async def get_events(self, task_id: str) -> list[dict[str, Any]]:
        raw_events = await self._client.lrange(self._events_key(task_id), 0, -1)
        events: list[dict[str, Any]] = []
        for raw in raw_events:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            events.append(json.loads(raw))
        return events
