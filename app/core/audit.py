from __future__ import annotations

import json
import logging

from fastapi import Request

from app.storage.task_store import RedisTaskStore

_AUDIT_LOGGER = logging.getLogger("app.audit")


async def emit_audit_event(
    request: Request,
    *,
    action: str,
    outcome: str,
    store: RedisTaskStore | None = None,
    **fields,
) -> dict[str, object]:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else None
    if not client_ip:
        client = getattr(request, "client", None)
        client_ip = getattr(client, "host", "unknown")

    payload = {
        "action": action,
        "outcome": outcome,
        "request_id": getattr(request.state, "request_id", None),
        "path": request.url.path,
        "method": request.method,
        "client_ip": client_ip or "unknown",
    }
    payload.update(fields)
    _AUDIT_LOGGER.info(json.dumps(payload, separators=(",", ":")))
    if store is not None:
        await store.append_audit_event(payload)
    return payload
