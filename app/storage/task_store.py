from __future__ import annotations

import hmac
import json
from typing import Any

from app.core.models import AnalysisResult, TaskListItem, TaskListPage, TaskState, TaskStatus
from app.core.models import TaskChatMessage


class RedisTaskStore:
    def __init__(
        self,
        client,
        prefix: str = "tasks",
        ttl_seconds: int | None = None,
        audit_max_events: int = 1000,
    ) -> None:
        self._client = client
        self._prefix = prefix
        self._ttl_seconds = ttl_seconds
        self._audit_max_events = audit_max_events

    def _status_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:status"

    def _result_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:result"

    def _events_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:events"

    def _task_access_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:access"

    def _task_request_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:request"

    def _task_cancel_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:cancel"

    def _task_chat_key(self, task_id: str) -> str:
        return f"{self._prefix}:{task_id}:chat"

    def _task_index_key(self) -> str:
        return f"{self._prefix}:index:tasks"

    def _rate_limit_key(self, bucket: str) -> str:
        return f"{self._prefix}:ratelimit:{bucket}"

    def _metric_key(self, name: str) -> str:
        return f"{self._prefix}:metrics:{name}"

    def _audit_events_key(self) -> str:
        return f"{self._prefix}:audit:events"

    async def set_status(self, status: TaskStatus) -> None:
        payload = status.model_dump_json()
        key = self._status_key(status.task_id)
        await self._client.set(key, payload)
        await self._client.lrem(self._task_index_key(), 0, status.task_id)
        await self._client.lpush(self._task_index_key(), status.task_id)
        await self._apply_ttl(key)

    async def get_status(self, task_id: str) -> TaskStatus | None:
        raw = await self._client.get(self._status_key(task_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return TaskStatus.model_validate_json(raw)

    async def set_result(self, task_id: str, result: AnalysisResult | dict[str, Any]) -> None:
        validated = AnalysisResult.model_validate(result)
        key = self._result_key(task_id)
        await self._client.set(key, validated.model_dump_json())
        await self._apply_ttl(key)

    async def get_result(self, task_id: str) -> AnalysisResult | None:
        raw = await self._client.get(self._result_key(task_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return AnalysisResult.model_validate_json(raw)

    async def append_event(self, task_id: str, event: dict[str, Any]) -> int:
        payload = json.dumps(event, default=str)
        key = self._events_key(task_id)
        result = await self._client.rpush(key, payload)
        await self._apply_ttl(key)
        return result

    async def append_chat_message(self, task_id: str, message: TaskChatMessage | dict[str, Any]) -> int:
        validated = TaskChatMessage.model_validate(message)
        key = self._task_chat_key(task_id)
        result = await self._client.rpush(key, validated.model_dump_json())
        await self._apply_ttl(key)
        return result

    async def get_chat_messages(self, task_id: str) -> list[TaskChatMessage]:
        raw_messages = await self._client.lrange(self._task_chat_key(task_id), 0, -1)
        messages: list[TaskChatMessage] = []
        for raw in raw_messages:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            messages.append(TaskChatMessage.model_validate_json(raw))
        return messages

    async def get_events(self, task_id: str) -> list[dict[str, Any]]:
        raw_events = await self._client.lrange(self._events_key(task_id), 0, -1)
        events: list[dict[str, Any]] = []
        for raw in raw_events:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            events.append(json.loads(raw))
        return events

    async def get_events_since(self, task_id: str, start_index: int) -> list[dict[str, Any]]:
        raw_events = await self._client.lrange(self._events_key(task_id), start_index, -1)
        events: list[dict[str, Any]] = []
        for raw in raw_events:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            events.append(json.loads(raw))
        return events

    async def append_audit_event(self, event: dict[str, Any]) -> int:
        payload = json.dumps(event, default=str)
        key = self._audit_events_key()
        result = await self._client.lpush(key, payload)
        if self._audit_max_events > 0:
            await self._client.ltrim(key, 0, self._audit_max_events - 1)
        await self._apply_ttl(key)
        return result

    async def get_audit_events(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        bounded_limit = max(0, limit)
        bounded_offset = max(0, offset)
        events: list[dict[str, Any]] = []
        if bounded_limit == 0:
            return {"events": [], "total": 0, "limit": 0, "offset": bounded_offset}

        raw_events = await self._client.lrange(self._audit_events_key(), 0, -1)
        normalized_filters = {
            key: value for key, value in (filters or {}).items() if isinstance(value, str) and value.strip()
        }
        for raw in raw_events:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            event = json.loads(raw)
            if not isinstance(event, dict):
                continue
            if normalized_filters and any(str(event.get(key, "")) != value for key, value in normalized_filters.items()):
                continue
            events.append(event)
        total = len(events)
        paged_events = events[bounded_offset : bounded_offset + bounded_limit]
        return {
            "events": paged_events,
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    async def delete_task(self, task_id: str) -> int:
        await self._client.lrem(self._task_index_key(), 0, task_id)
        return await self._client.delete(
            self._status_key(task_id),
            self._result_key(task_id),
            self._events_key(task_id),
            self._task_access_key(task_id),
            self._task_request_key(task_id),
            self._task_cancel_key(task_id),
            self._task_chat_key(task_id),
        )

    async def ping(self) -> bool:
        return bool(await self._client.ping())

    async def hit_rate_limit(self, bucket: str, *, limit: int, window_seconds: int) -> dict[str, int | bool]:
        key = self._rate_limit_key(bucket)
        current = await self._client.incr(key)
        ttl = await self._client.ttl(key)
        if current == 1 or ttl in {-1, -2}:
            await self._client.expire(key, window_seconds)
            ttl = window_seconds
        retry_after = int(ttl if ttl and ttl > 0 else window_seconds)
        allowed = current <= limit
        remaining = max(limit - current, 0)
        return {
            "allowed": allowed,
            "limit": limit,
            "remaining": remaining,
            "retry_after": retry_after,
        }

    async def increment_metric(self, name: str, *, amount: int = 1) -> int:
        return await self._client.incrby(self._metric_key(name), amount)

    async def set_task_access_token(self, task_id: str, token: str) -> None:
        key = self._task_access_key(task_id)
        await self._client.set(key, token)
        await self._apply_ttl(key)

    async def set_task_request(self, task_id: str, payload: dict[str, Any]) -> None:
        key = self._task_request_key(task_id)
        await self._client.set(key, json.dumps(payload, default=str))
        await self._apply_ttl(key)

    async def get_task_request(self, task_id: str) -> dict[str, Any] | None:
        raw = await self._client.get(self._task_request_key(task_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def request_task_cancel(self, task_id: str) -> None:
        key = self._task_cancel_key(task_id)
        await self._client.set(key, "1")
        await self._apply_ttl(key)

    async def is_task_cancel_requested(self, task_id: str) -> bool:
        raw = await self._client.get(self._task_cancel_key(task_id))
        return raw is not None

    async def clear_task_cancel_request(self, task_id: str) -> None:
        await self._client.delete(self._task_cancel_key(task_id))

    async def has_task_access_token(self, task_id: str, token: str) -> bool:
        raw = await self._client.get(self._task_access_key(task_id))
        if raw is None:
            return False
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return hmac.compare_digest(str(raw), token)

    async def get_metrics_snapshot(self) -> dict[str, int]:
        pattern = self._metric_key("*")
        keys = await self._client.keys(pattern)
        metrics: dict[str, int] = {}
        prefix = self._metric_key("")
        for raw_key in keys:
            key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
            value = await self._client.get(key)
            if isinstance(value, bytes):
                value = value.decode("utf-8")
            metrics[key.replace(prefix, "", 1)] = int(value)
        return metrics

    async def list_tasks(
        self,
        *,
        limit: int = 25,
        offset: int = 0,
        state: TaskState | None = None,
    ) -> TaskListPage:
        bounded_limit = max(0, limit)
        bounded_offset = max(0, offset)
        if bounded_limit == 0:
            return TaskListPage(tasks=[], total=0, limit=0, offset=bounded_offset)

        raw_task_ids = await self._client.lrange(self._task_index_key(), 0, -1)
        ordered_task_ids: list[str] = []
        seen: set[str] = set()
        for raw_task_id in raw_task_ids:
            task_id = raw_task_id.decode("utf-8") if isinstance(raw_task_id, bytes) else str(raw_task_id)
            if task_id in seen:
                continue
            seen.add(task_id)
            ordered_task_ids.append(task_id)

        items: list[TaskListItem] = []
        for task_id in ordered_task_ids:
            status_payload = await self.get_status(task_id)
            if status_payload is None:
                continue
            if state is not None and status_payload.state is not state:
                continue
            task_request = await self.get_task_request(task_id)
            github_url = task_request.get("github_url") if isinstance(task_request, dict) else None
            items.append(TaskListItem(**status_payload.model_dump(), github_url=github_url if isinstance(github_url, str) else None))

        total = len(items)
        return TaskListPage(
            tasks=items[bounded_offset : bounded_offset + bounded_limit],
            total=total,
            limit=bounded_limit,
            offset=bounded_offset,
        )

    async def _apply_ttl(self, key: str) -> None:
        if self._ttl_seconds is None or self._ttl_seconds <= 0:
            return
        await self._client.expire(key, self._ttl_seconds)
