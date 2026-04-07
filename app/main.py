from __future__ import annotations

import inspect
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from arq.connections import RedisSettings, create_pool

from app.api.routes.tasks import router as tasks_router
from app.core.config import Settings
from app.core.security import require_api_key_scopes
from app.storage.task_store import RedisTaskStore


_HTTP_LOGGER = logging.getLogger("app.http")
_AUDIT_LOGGER = logging.getLogger("app.audit")


async def _create_redis_client(redis_url: str):
    return await create_pool(RedisSettings.from_dsn(redis_url))


def _configure_logging(settings: Settings) -> None:
    log_level = getattr(settings, "log_level", "INFO")
    resolved_level = getattr(logging, str(log_level).upper(), logging.INFO)
    logging.basicConfig(level=resolved_level)
    _HTTP_LOGGER.setLevel(resolved_level)
    _AUDIT_LOGGER.setLevel(resolved_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if getattr(app.state, "task_store", None) is not None:
        yield
        return

    settings = Settings()
    _configure_logging(settings)
    app.state.settings = settings
    client = await _create_redis_client(settings.redis_url)
    app.state.redis_client = client
    app.state.arq_redis = client
    app.state.task_store = RedisTaskStore(
        client,
        ttl_seconds=getattr(settings, "task_ttl_seconds", None),
        audit_max_events=getattr(settings, "audit_max_events", 1000),
    )
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
    app.state.settings = Settings()
    _configure_logging(app.state.settings)
    if task_store is not None:
        app.state.task_store = task_store
        app.state.redis_client = getattr(task_store, "_client", None)

    @app.middleware("http")
    async def apply_cors(request: Request, call_next):
        settings = getattr(app.state, "settings", None)
        origin = request.headers.get("origin")
        allowed_origins = set(getattr(settings, "cors_allowed_origins", ()))
        if origin and origin in allowed_origins and request.method == "OPTIONS":
            response = Response(status_code=status.HTTP_200_OK)
        else:
            response = await call_next(request)

        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "DELETE,GET,OPTIONS,PATCH,POST,PUT"
            response.headers["Access-Control-Allow-Headers"] = request.headers.get(
                "Access-Control-Request-Headers",
                "Authorization,Content-Type,X-Request-ID",
            )
            response.headers["Vary"] = "Origin"
        return response

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid4().hex
        request.state.request_id = request_id
        started_at = time.perf_counter()
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        settings = getattr(app.state, "settings", None)
        if settings is None or settings.request_log_enabled:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            _HTTP_LOGGER.info(
                json.dumps(
                    {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    },
                    separators=(",", ":"),
                )
            )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None) or uuid4().hex
        _HTTP_LOGGER.error(
            json.dumps(
                {
                    "request_id": request_id,
                    "path": request.url.path,
                    "method": request.method,
                    "error": str(exc),
                },
                separators=(",", ":"),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error.", "request_id": request_id},
            headers={"X-Request-ID": request_id},
        )
    
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        client = getattr(app.state, "redis_client", None)
        if client is None:
            store = getattr(app.state, "task_store", None)
            if store is None:
                return {"status": "ready"}
            client = getattr(store, "_client", None)
        try:
            if client is not None and await client.ping():
                return {"status": "ready"}
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis is not ready.") from exc
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redis is not ready.")

    @app.get("/metrics")
    async def metrics(request: Request) -> Response:
        store = getattr(app.state, "task_store", None)
        if store is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Task store is not configured.")
        settings = getattr(app.state, "settings", None)
        if settings is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Settings are not configured.")
        await require_api_key_scopes(request, settings, required_scopes=("metrics:read",), store=store)
        snapshot = await store.get_metrics_snapshot()
        lines = [f"{name} {value}" for name, value in sorted(snapshot.items())]
        body = "\n".join(lines) + ("\n" if lines else "")
        return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.get("/api/v1/audit/events")
    async def audit_events(
        request: Request,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        outcome: str | None = None,
        task_id: str | None = None,
        request_id: str | None = None,
        subject: str | None = None,
        method: str | None = None,
        path: str | None = None,
    ) -> dict[str, object]:
        store = getattr(app.state, "task_store", None)
        if store is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Task store is not configured.")
        settings = getattr(app.state, "settings", None)
        if settings is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Settings are not configured.")
        await require_api_key_scopes(request, settings, required_scopes=("audit:read",), store=store)
        bounded_limit = min(max(limit, 1), 500)
        bounded_offset = max(offset, 0)
        filters = {
            "action": action or "",
            "outcome": outcome or "",
            "task_id": task_id or "",
            "request_id": request_id or "",
            "subject": subject or "",
            "method": method or "",
            "path": path or "",
        }
        return await store.get_audit_events(limit=bounded_limit, offset=bounded_offset, filters=filters)

    app.include_router(tasks_router, prefix="/api/v1")
    return app


app = create_app()
