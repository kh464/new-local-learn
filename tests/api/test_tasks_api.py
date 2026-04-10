import json

import httpx
import pytest
import jwt
from jwt.utils import base64url_encode

from app.core.models import TaskStage, TaskState, TaskStatus
from app.main import create_app
from app.storage.task_store import RedisTaskStore


def _build_oidc_test_bundle(*, scopes: str = "analyze:create tasks:read") -> tuple[str, dict[str, object], dict[str, str]]:
    secret = b"oidc-shared-secret-1234567890-abcdef"
    issuer = "https://issuer.example.test/realms/local"
    audience = "local-learn-api"
    kid = "oidc-test-key"
    token = jwt.encode(
        {
            "iss": issuer,
            "aud": audience,
            "sub": "user-123",
            "preferred_username": "vacation-user",
            "scope": scopes,
        },
        secret,
        algorithm="HS256",
        headers={"kid": kid},
    )
    jwks = {
        "keys": [
            {
                "kty": "oct",
                "k": base64url_encode(secret).decode("utf-8"),
                "kid": kid,
                "alg": "HS256",
                "use": "sig",
            }
        ]
    }
    settings = {
        "oidc_issuer_url": issuer,
        "oidc_audience": audience,
        "oidc_jwks_url": f"{issuer}/protocol/openid-connect/certs",
        "oidc_algorithms": ("HS256",),
        "oidc_subject_claim": "preferred_username",
        "oidc_scope_claim": "scope",
    }
    return token, jwks, settings


async def test_app_lifespan_initializes_task_store(monkeypatch):
    from app import main as app_main

    class FakeRedis:
        def __init__(self):
            self.closed = False
            self._connection_pool = self.ConnectionPool()

        async def aclose(self):
            self.closed = True

        class ConnectionPool:
            def __init__(self):
                self.disconnected = False

            async def disconnect(self):
                self.disconnected = True

        @property
        def connection_pool(self):
            return self._connection_pool

    client = FakeRedis()

    monkeypatch.setattr(app_main, "Settings", lambda: type("S", (), {"redis_url": "redis://test/0"}))
    async def fake_create_redis_client(url: str):
        return client

    monkeypatch.setattr(app_main, "_create_redis_client", fake_create_redis_client)

    app = app_main.create_app()
    async with app.router.lifespan_context(app):
        assert app.state.redis_client is client
        assert isinstance(app.state.task_store, RedisTaskStore)
    assert client.closed is True
    assert client.connection_pool.disconnected is True


async def test_analyze_endpoint_returns_urls(api_client, monkeypatch):
    async def fake_enqueue(*, store, queue, task_id: str, github_url: str, task_token: str) -> str:
        return task_id

    monkeypatch.setattr("app.api.routes.tasks.enqueue_analysis", fake_enqueue)
    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )
    assert response.status_code == 202
    payload = response.json()
    task_id = payload["task_id"]
    assert payload["status_url"] == f"/api/v1/tasks/{task_id}"
    assert payload["result_url"] == f"/api/v1/tasks/{task_id}/result"
    assert payload["stream_url"] == f"/api/v1/tasks/{task_id}/stream"
    assert isinstance(payload["task_token"], str)
    assert len(payload["task_token"]) >= 20


async def test_analyze_endpoint_persists_queued_status_and_enqueues_job(api_client):
    class FakeQueue:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        async def enqueue_job(self, job_name: str, task_id: str, github_url: str):
            self.calls.append((job_name, task_id, github_url))
            return object()

    queue = FakeQueue()
    api_client._transport.app.state.arq_redis = queue

    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )

    assert response.status_code == 202
    payload = response.json()
    task_id = payload["task_id"]
    assert queue.calls == [("run_analysis_job", task_id, "https://github.com/octocat/Hello-World")]

    status_response = await api_client.get(f"/api/v1/tasks/{task_id}")
    assert status_response.status_code == 200
    assert status_response.json()["state"] == TaskState.QUEUED.value
    assert status_response.json()["stage"] is None
    assert status_response.json()["progress"] == 0
    assert response.headers["x-ratelimit-limit"] == "10"
    assert response.headers["x-ratelimit-remaining"] == "9"
    assert await api_client._transport.app.state.task_store.get_task_request(task_id) == {
        "github_url": "https://github.com/octocat/Hello-World",
    }


async def test_analyze_endpoint_returns_503_when_queue_missing(api_client):
    delattr(api_client._transport.app.state, "arq_redis")

    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Task queue is not configured."


async def test_analyze_endpoint_rejects_non_github_hosts(api_client):
    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://gitlab.com/octocat/Hello-World"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported GitHub host: gitlab.com"


async def test_analyze_endpoint_rate_limits_repeat_requests(api_client):
    app = api_client._transport.app
    app.state.settings.rate_limit_max_requests = 1
    app.state.settings.rate_limit_window_seconds = 60

    first = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )
    second = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json()["detail"] == "Rate limit exceeded."
    assert second.headers["retry-after"] == "60"
    assert second.headers["x-ratelimit-limit"] == "1"
    assert second.headers["x-ratelimit-remaining"] == "0"
    metrics = await app.state.task_store.get_metrics_snapshot()
    assert metrics["analyze_rate_limited_total"] == 1


async def test_analyze_endpoint_requires_api_key_when_configured(api_client):
    api_client._transport.app.state.settings.api_keys = ("secret-key",)

    missing = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )
    invalid = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
        headers={"X-API-Key": "wrong"},
    )
    valid = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
        headers={"X-API-Key": "secret-key"},
    )

    assert missing.status_code == 401
    assert missing.json()["detail"] == "Invalid or missing API key."
    assert invalid.status_code == 401
    assert valid.status_code == 202
    metrics = await api_client._transport.app.state.task_store.get_metrics_snapshot()
    assert metrics["api_auth_failures_total"] == 2


async def test_analyze_endpoint_enforces_api_key_scope_when_records_configured(api_client):
    api_client._transport.app.state.settings.api_key_records = (
        "reader:reader-secret:tasks:read|metrics:read",
        "writer:writer-secret:analyze:create|tasks:read",
    )

    denied = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
        headers={"X-API-Key": "reader-secret"},
    )
    allowed = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
        headers={"X-API-Key": "writer-secret"},
    )

    assert denied.status_code == 403
    assert denied.json()["detail"] == "API key is not authorized for this action."
    assert allowed.status_code == 202


async def test_analyze_endpoint_accepts_valid_oidc_bearer_token(api_client, monkeypatch):
    token, jwks, settings = _build_oidc_test_bundle(scopes="analyze:create tasks:read")
    app = api_client._transport.app
    for key, value in settings.items():
        setattr(app.state.settings, key, value)

    async def fake_fetch(url: str, **kwargs):
        assert url == settings["oidc_jwks_url"]
        return jwks

    monkeypatch.setattr("app.core.security.fetch_oidc_jwks", fake_fetch, raising=False)

    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202


async def test_metrics_endpoint_enforces_oidc_scope(api_client, monkeypatch):
    token, jwks, settings = _build_oidc_test_bundle(scopes="tasks:read")
    app = api_client._transport.app
    for key, value in settings.items():
        setattr(app.state.settings, key, value)

    async def fake_fetch(url: str, **kwargs):
        assert url == settings["oidc_jwks_url"]
        return jwks

    monkeypatch.setattr("app.core.security.fetch_oidc_jwks", fake_fetch, raising=False)

    response = await api_client.get("/metrics", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Bearer token is not authorized for this action."


async def test_analyze_endpoint_cleans_up_task_if_enqueue_fails(api_client):
    class ExplodingQueue:
        async def enqueue_job(self, job_name: str, task_id: str, github_url: str):
            raise RuntimeError("queue offline")

    app = api_client._transport.app
    app.state.arq_redis = ExplodingQueue()

    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Failed to enqueue analysis job."
    statuses = await app.state.task_store._client.keys("tasks:*:status")
    results = await app.state.task_store._client.keys("tasks:*:result")
    events = await app.state.task_store._client.keys("tasks:*:events")
    assert statuses == []
    assert results == []
    assert events == []


async def test_task_endpoints_return_status_result_and_events(api_client, fakeredis_client, sample_analysis_result):
    store = RedisTaskStore(fakeredis_client)
    status = TaskStatus(task_id="task-2", state=TaskState.SUCCEEDED, progress=100)
    await store.set_status(status)
    await store.set_result("task-2", sample_analysis_result)
    await store.append_event("task-2", {"message": "started"})

    status_response = await api_client.get("/api/v1/tasks/task-2")
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "succeeded"

    result_response = await api_client.get("/api/v1/tasks/task-2/result")
    assert result_response.status_code == 200
    assert result_response.json()["github_url"] == sample_analysis_result.github_url
    assert result_response.json()["backend_summary"]["routes"][0]["path"] == "/health"

    stream_response = await api_client.get("/api/v1/tasks/task-2/stream")
    assert stream_response.status_code == 200
    assert stream_response.headers["content-type"].startswith("text/event-stream")
    assert 'data: {"message":"started"}' in stream_response.text


async def test_tasks_list_endpoint_returns_recent_tasks(api_client, fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-list-1", state=TaskState.SUCCEEDED, progress=100))
    await store.set_task_request("task-list-1", {"github_url": "https://github.com/octocat/one"})
    await store.set_status(TaskStatus(task_id="task-list-2", state=TaskState.RUNNING, progress=40))
    await store.set_task_request("task-list-2", {"github_url": "https://github.com/octocat/two"})
    api_client._transport.app.state.task_store = store

    response = await api_client.get("/api/v1/tasks?limit=1&state=running")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert len(payload["tasks"]) == 1
    assert payload["tasks"][0]["task_id"] == "task-list-2"
    assert payload["tasks"][0]["state"] == "running"
    assert payload["tasks"][0]["progress"] == 40
    assert payload["tasks"][0]["github_url"] == "https://github.com/octocat/two"


async def test_tasks_list_endpoint_requires_tasks_read_scope_when_records_configured(api_client):
    api_client._transport.app.state.settings.api_key_records = (
        "writer:writer-secret:analyze:create|tasks:write",
        "reader:reader-secret:tasks:read",
    )

    denied = await api_client.get("/api/v1/tasks", headers={"X-API-Key": "writer-secret"})
    allowed = await api_client.get("/api/v1/tasks", headers={"X-API-Key": "reader-secret"})

    assert denied.status_code == 403
    assert denied.json()["detail"] == "API key is not authorized for this action."
    assert allowed.status_code == 200


async def test_task_endpoints_require_api_key_when_configured(api_client, fakeredis_client, sample_analysis_result):
    store = RedisTaskStore(fakeredis_client)
    status = TaskStatus(task_id="task-auth", state=TaskState.SUCCEEDED, progress=100)
    await store.set_status(status)
    await store.set_result("task-auth", sample_analysis_result)
    await store.append_event("task-auth", {"message": "started"})
    await store.set_task_access_token("task-auth", "task-token-123")

    app = api_client._transport.app
    app.state.task_store = store
    app.state.settings.api_keys = ("task-secret",)

    missing_status = await api_client.get("/api/v1/tasks/task-auth")
    valid_status = await api_client.get("/api/v1/tasks/task-auth", headers={"X-API-Key": "task-secret"})
    token_status = await api_client.get("/api/v1/tasks/task-auth", headers={"X-Task-Token": "task-token-123"})
    missing_result = await api_client.get("/api/v1/tasks/task-auth/result")
    valid_result = await api_client.get("/api/v1/tasks/task-auth/result", headers={"X-API-Key": "task-secret"})
    token_result = await api_client.get("/api/v1/tasks/task-auth/result", headers={"X-Task-Token": "task-token-123"})
    missing_stream = await api_client.get("/api/v1/tasks/task-auth/stream")
    valid_stream = await api_client.get("/api/v1/tasks/task-auth/stream?api_key=task-secret")
    token_stream = await api_client.get("/api/v1/tasks/task-auth/stream?task_token=task-token-123")

    assert missing_status.status_code == 401
    assert valid_status.status_code == 200
    assert token_status.status_code == 200
    assert missing_result.status_code == 401
    assert valid_result.status_code == 200
    assert token_result.status_code == 200
    assert missing_stream.status_code == 401
    assert valid_stream.status_code == 200
    assert token_stream.status_code == 200


async def test_task_status_endpoint_accepts_valid_oidc_bearer_token(api_client, fakeredis_client, monkeypatch):
    token, jwks, settings = _build_oidc_test_bundle(scopes="tasks:read")
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-oidc-auth", state=TaskState.RUNNING, progress=15))

    app = api_client._transport.app
    app.state.task_store = store
    for key, value in settings.items():
        setattr(app.state.settings, key, value)

    async def fake_fetch(url: str, **kwargs):
        assert url == settings["oidc_jwks_url"]
        return jwks

    monkeypatch.setattr("app.core.security.fetch_oidc_jwks", fake_fetch, raising=False)

    response = await api_client.get(
        "/api/v1/tasks/task-oidc-auth",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["task_id"] == "task-oidc-auth"


async def test_task_artifact_endpoint_downloads_markdown(api_client, fakeredis_client, sample_analysis_result):
    store = RedisTaskStore(fakeredis_client)
    status = TaskStatus(task_id="task-artifact-md", state=TaskState.SUCCEEDED, progress=100)
    await store.set_status(status)
    await store.set_result("task-artifact-md", sample_analysis_result.model_copy(update={"markdown_path": sample_analysis_result.markdown_path}))

    api_client._transport.app.state.task_store = store

    response = await api_client.get("/api/v1/tasks/task-artifact-md/artifacts/markdown")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-disposition"] == 'attachment; filename="result.md"'
    assert response.content.decode("utf-8").replace("\r\n", "\n") == "# Result\n"


@pytest.mark.parametrize(
    ("artifact_kind", "media_type", "body", "suffix"),
    [
        ("html", "text/html", "<h1>Result</h1>\n", ".html"),
        ("pdf", "application/pdf", "%PDF-1.4\n", ".pdf"),
    ],
)
async def test_task_artifact_endpoint_downloads_supported_artifacts(
    api_client,
    fakeredis_client,
    sample_analysis_result,
    artifact_kind,
    media_type,
    body,
    suffix,
):
    store = RedisTaskStore(fakeredis_client)
    status = TaskStatus(task_id=f"task-artifact-{artifact_kind}", state=TaskState.SUCCEEDED, progress=100)
    await store.set_status(status)

    artifact_path = sample_analysis_result.markdown_path.replace(".md", suffix)
    if suffix == ".pdf":
        with open(artifact_path, "wb") as handle:
            handle.write(body.encode("utf-8"))
    else:
        with open(artifact_path, "w", encoding="utf-8") as handle:
            handle.write(body)
    await store.set_result(
        status.task_id,
        sample_analysis_result.model_copy(update={f"{artifact_kind}_path": artifact_path}),
    )

    api_client._transport.app.state.task_store = store

    response = await api_client.get(f"/api/v1/tasks/{status.task_id}/artifacts/{artifact_kind}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media_type)
    assert response.headers["content-disposition"] == f'attachment; filename="result{suffix}"'
    if artifact_kind == "pdf":
        assert response.content == body.encode("utf-8")
    else:
        assert response.content.decode("utf-8").replace("\r\n", "\n") == body


async def test_task_artifact_endpoint_requires_task_access_when_configured(
    api_client, fakeredis_client, sample_analysis_result
):
    store = RedisTaskStore(fakeredis_client)
    status = TaskStatus(task_id="task-artifact-auth", state=TaskState.SUCCEEDED, progress=100)
    await store.set_status(status)
    await store.set_result("task-artifact-auth", sample_analysis_result)
    await store.set_task_access_token("task-artifact-auth", "artifact-token-123")

    app = api_client._transport.app
    app.state.task_store = store
    app.state.settings.api_keys = ("artifact-secret",)

    missing = await api_client.get("/api/v1/tasks/task-artifact-auth/artifacts/markdown")
    valid = await api_client.get(
        "/api/v1/tasks/task-artifact-auth/artifacts/markdown",
        headers={"X-API-Key": "artifact-secret"},
    )
    token = await api_client.get(
        "/api/v1/tasks/task-artifact-auth/artifacts/markdown?task_token=artifact-token-123"
    )

    assert missing.status_code == 401
    assert valid.status_code == 200
    assert token.status_code == 200


async def test_task_artifact_endpoint_returns_404_when_artifact_file_is_missing(
    api_client, fakeredis_client, sample_analysis_result
):
    store = RedisTaskStore(fakeredis_client)
    status = TaskStatus(task_id="task-artifact-missing", state=TaskState.SUCCEEDED, progress=100)
    await store.set_status(status)
    await store.set_result("task-artifact-missing", sample_analysis_result.model_copy(update={"markdown_path": str(sample_analysis_result.repo_path) + "/missing.md"}))

    api_client._transport.app.state.task_store = store

    response = await api_client.get("/api/v1/tasks/task-artifact-missing/artifacts/markdown")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task artifact not found."


async def test_task_stream_returns_404_for_unknown_task(api_client):
    response = await api_client.get("/api/v1/tasks/missing-task/stream")

    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found."


async def test_task_stream_polls_until_terminal_state(api_client, monkeypatch):
    from app.api.routes import tasks as tasks_module

    class SequencedStore:
        def __init__(self) -> None:
            self.event_calls = 0

        async def get_events_since(self, task_id: str, start_index: int):
            batches = [
                [{"state": "running", "progress": 10}],
                [{"state": "succeeded", "progress": 100}],
            ]
            if self.event_calls >= len(batches):
                return []
            batch = batches[self.event_calls]
            self.event_calls += 1
            return batch

        async def get_status(self, task_id: str):
            if self.event_calls < 2:
                return TaskStatus(task_id=task_id, state=TaskState.RUNNING, progress=10)
            return TaskStatus(task_id=task_id, state=TaskState.SUCCEEDED, progress=100)

    monkeypatch.setattr(tasks_module, "_STREAM_POLL_INTERVAL_SECONDS", 0)
    api_client._transport.app.state.task_store = SequencedStore()

    response = await api_client.get("/api/v1/tasks/task-3/stream")

    assert response.status_code == 200
    assert 'data: {"state":"running","progress":10}' in response.text
    assert 'data: {"state":"succeeded","progress":100}' in response.text


async def test_healthz_returns_ok(api_client):
    response = await api_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


async def test_request_id_header_is_propagated(api_client):
    response = await api_client.get("/healthz", headers={"X-Request-ID": "vacation-check-123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "vacation-check-123"


async def test_request_logging_emits_structured_record(api_client, caplog):
    caplog.set_level("INFO", logger="app.http")

    response = await api_client.get("/healthz", headers={"X-Request-ID": "log-check-1"})

    assert response.status_code == 200
    log_line = next(record.message for record in caplog.records if record.name == "app.http")
    payload = json.loads(log_line)
    assert payload["request_id"] == "log-check-1"
    assert payload["method"] == "GET"
    assert payload["path"] == "/healthz"
    assert payload["status_code"] == 200
    assert isinstance(payload["duration_ms"], int)


async def test_analyze_endpoint_emits_audit_record_on_accept(api_client, monkeypatch, caplog):
    async def fake_enqueue(*, store, queue, task_id: str, github_url: str, task_token: str) -> str:
        return task_id

    monkeypatch.setattr("app.api.routes.tasks.enqueue_analysis", fake_enqueue)
    caplog.set_level("INFO", logger="app.audit")

    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
        headers={"X-Request-ID": "audit-analyze-1"},
    )

    assert response.status_code == 202
    payload = response.json()
    audit_record = next(json.loads(record.message) for record in caplog.records if record.name == "app.audit")
    assert audit_record["action"] == "analyze_submit"
    assert audit_record["outcome"] == "accepted"
    assert audit_record["request_id"] == "audit-analyze-1"
    assert audit_record["task_id"] == payload["task_id"]
    assert audit_record["github_url"] == "https://github.com/octocat/Hello-World"


async def test_api_key_failure_emits_audit_record(api_client, caplog):
    api_client._transport.app.state.settings.api_keys = ("audit-secret",)
    caplog.set_level("INFO", logger="app.audit")

    response = await api_client.post(
        "/api/v1/analyze",
        json={"github_url": "https://github.com/octocat/Hello-World"},
        headers={"X-Request-ID": "audit-auth-1"},
    )

    assert response.status_code == 401
    audit_record = next(json.loads(record.message) for record in caplog.records if record.name == "app.audit")
    assert audit_record["action"] == "api_key_auth"
    assert audit_record["outcome"] == "denied"
    assert audit_record["request_id"] == "audit-auth-1"
    assert audit_record["path"] == "/api/v1/analyze"


async def test_task_artifact_download_emits_audit_record(
    api_client, fakeredis_client, sample_analysis_result, caplog
):
    store = RedisTaskStore(fakeredis_client)
    status = TaskStatus(task_id="task-audit-artifact", state=TaskState.SUCCEEDED, progress=100)
    await store.set_status(status)
    await store.set_result("task-audit-artifact", sample_analysis_result)
    api_client._transport.app.state.task_store = store
    caplog.set_level("INFO", logger="app.audit")

    response = await api_client.get(
        "/api/v1/tasks/task-audit-artifact/artifacts/markdown",
        headers={"X-Request-ID": "audit-artifact-1"},
    )

    assert response.status_code == 200
    audit_record = next(json.loads(record.message) for record in caplog.records if record.name == "app.audit")
    assert audit_record["action"] == "task_artifact_download"
    assert audit_record["outcome"] == "success"
    assert audit_record["request_id"] == "audit-artifact-1"
    assert audit_record["task_id"] == "task-audit-artifact"
    assert audit_record["artifact_kind"] == "markdown"


async def test_unhandled_exceptions_return_request_id(caplog, fakeredis_client):
    caplog.set_level("ERROR", logger="app.http")
    app = create_app(task_store=RedisTaskStore(fakeredis_client))

    @app.get("/boom")
    async def boom():
        raise RuntimeError("unexpected")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom", headers={"X-Request-ID": "boom-1"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error.", "request_id": "boom-1"}
    assert any("boom-1" in record.message for record in caplog.records if record.name == "app.http")


async def test_task_stream_uses_configured_poll_interval(api_client, monkeypatch):
    from app.api.routes import tasks as tasks_module

    class PendingStore:
        def __init__(self) -> None:
            self.calls = 0

        async def get_events_since(self, task_id: str, start_index: int):
            self.calls += 1
            return []

        async def get_status(self, task_id: str):
            if self.calls >= 2:
                return TaskStatus(task_id=task_id, state=TaskState.SUCCEEDED, progress=100)
            return TaskStatus(task_id=task_id, state=TaskState.RUNNING, progress=10)

    sleep_calls: list[float] = []

    async def fake_sleep(value: float):
        sleep_calls.append(value)

    api_client._transport.app.state.task_store = PendingStore()
    api_client._transport.app.state.settings.stream_poll_interval_seconds = 0.25
    monkeypatch.setattr(tasks_module.asyncio, "sleep", fake_sleep)

    response = await api_client.get("/api/v1/tasks/task-9/stream")

    assert response.status_code == 200
    assert sleep_calls == [0.25]


async def test_readyz_returns_ready(api_client):
    response = await api_client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_readyz_returns_503_when_redis_ping_fails(api_client):
    class BrokenRedis:
        async def ping(self):
            raise RuntimeError("down")

    api_client._transport.app.state.redis_client = BrokenRedis()

    response = await api_client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"] == "Redis is not ready."


async def test_cors_allows_configured_origin(fakeredis_client):
    app = create_app(task_store=RedisTaskStore(fakeredis_client))
    app.state.settings.cors_allowed_origins = ("https://app.example.com",)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/analyze",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"


async def test_metrics_endpoint_exposes_prometheus_text(api_client):
    app = api_client._transport.app
    await app.state.task_store.increment_metric("analyze_requests_total", amount=2)
    await app.state.task_store.increment_metric("analysis_jobs_succeeded_total")

    response = await api_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "analyze_requests_total 2" in response.text
    assert "analysis_jobs_succeeded_total 1" in response.text


async def test_metrics_endpoint_requires_api_key_when_configured(api_client):
    api_client._transport.app.state.settings.api_keys = ("metrics-key",)

    missing = await api_client.get("/metrics")
    valid = await api_client.get("/metrics", headers={"X-API-Key": "metrics-key"})

    assert missing.status_code == 401
    assert missing.json()["detail"] == "Invalid or missing API key."
    assert valid.status_code == 200


async def test_metrics_endpoint_enforces_api_key_scope_when_records_configured(api_client):
    api_client._transport.app.state.settings.api_key_records = (
        "analyzer:analyze-secret:analyze:create|tasks:read",
        "ops:ops-secret:metrics:read",
    )

    denied = await api_client.get("/metrics", headers={"X-API-Key": "analyze-secret"})
    allowed = await api_client.get("/metrics", headers={"X-API-Key": "ops-secret"})

    assert denied.status_code == 403
    assert denied.json()["detail"] == "API key is not authorized for this action."
    assert allowed.status_code == 200


async def test_audit_events_endpoint_returns_latest_events(api_client):
    app = api_client._transport.app
    await app.state.task_store.append_audit_event({"action": "older", "outcome": "accepted"})
    await app.state.task_store.append_audit_event({"action": "newer", "outcome": "denied"})

    response = await api_client.get("/api/v1/audit/events?limit=1")

    assert response.status_code == 200
    assert response.json() == {
        "events": [
            {"action": "newer", "outcome": "denied"},
        ],
        "total": 2,
        "limit": 1,
        "offset": 0,
    }


async def test_audit_events_endpoint_supports_filters_and_offsets(api_client):
    app = api_client._transport.app
    await app.state.task_store.append_audit_event(
        {"action": "task_artifact_download", "outcome": "success", "task_id": "task-1", "subject": "worker"}
    )
    await app.state.task_store.append_audit_event(
        {"action": "task_artifact_download", "outcome": "success", "task_id": "task-2", "subject": "worker"}
    )
    await app.state.task_store.append_audit_event(
        {"action": "analyze_submit", "outcome": "accepted", "task_id": "task-3", "subject": "api"}
    )

    response = await api_client.get(
        "/api/v1/audit/events?limit=1&offset=1&action=task_artifact_download&subject=worker"
    )

    assert response.status_code == 200
    assert response.json() == {
        "events": [
            {"action": "task_artifact_download", "outcome": "success", "task_id": "task-1", "subject": "worker"}
        ],
        "total": 2,
        "limit": 1,
        "offset": 1,
    }


async def test_audit_events_endpoint_requires_audit_scope_when_records_configured(api_client):
    api_client._transport.app.state.settings.api_key_records = (
        "metrics:metrics-secret:metrics:read",
        "auditor:auditor-secret:audit:read",
    )

    denied = await api_client.get("/api/v1/audit/events", headers={"X-API-Key": "metrics-secret"})
    allowed = await api_client.get("/api/v1/audit/events", headers={"X-API-Key": "auditor-secret"})

    assert denied.status_code == 403
    assert denied.json()["detail"] == "API key is not authorized for this action."
    assert allowed.status_code == 200


async def test_task_artifact_download_includes_security_headers(api_client, fakeredis_client, sample_analysis_result):
    store = RedisTaskStore(fakeredis_client)
    status = TaskStatus(task_id="task-secure-artifact", state=TaskState.SUCCEEDED, progress=100)
    await store.set_status(status)
    await store.set_result("task-secure-artifact", sample_analysis_result)
    api_client._transport.app.state.task_store = store

    response = await api_client.get("/api/v1/tasks/task-secure-artifact/artifacts/markdown")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_cancel_endpoint_marks_queued_task_cancelled(api_client, fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-cancel", state=TaskState.QUEUED, progress=0))
    await store.set_task_request("task-cancel", {"github_url": "https://github.com/octocat/Hello-World"})
    api_client._transport.app.state.task_store = store

    response = await api_client.post("/api/v1/tasks/task-cancel/cancel")

    assert response.status_code == 202
    assert response.json()["state"] == "cancelled"
    status = await store.get_status("task-cancel")
    assert status is not None
    assert status.state is TaskState.CANCELLED
    assert await store.is_task_cancel_requested("task-cancel") is True


async def test_stop_endpoint_marks_running_task_as_stop_requested(api_client, fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(
        TaskStatus(
            task_id="task-stop",
            state=TaskState.RUNNING,
            stage=TaskStage.SCAN_TREE,
            progress=20,
        )
    )
    await store.set_task_request("task-stop", {"github_url": "https://github.com/octocat/Hello-World"})
    api_client._transport.app.state.task_store = store

    response = await api_client.post("/api/v1/tasks/task-stop/stop")

    assert response.status_code == 202
    assert response.json()["state"] == "running"
    assert response.json()["message"] == "Cancellation requested."
    assert await store.is_task_cancel_requested("task-stop") is True


async def test_retry_endpoint_requeues_failed_task(api_client, fakeredis_client):
    class FakeQueue:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        async def enqueue_job(self, job_name: str, task_id: str, github_url: str):
            self.calls.append((job_name, task_id, github_url))
            return object()

    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-retry", state=TaskState.FAILED, progress=100, error="boom"))
    await store.set_task_request("task-retry", {"github_url": "https://github.com/octocat/Hello-World"})
    api_client._transport.app.state.task_store = store
    api_client._transport.app.state.arq_redis = FakeQueue()

    response = await api_client.post("/api/v1/tasks/task-retry/retry")

    assert response.status_code == 202
    payload = response.json()
    assert payload["task_id"] != "task-retry"
    assert payload["status_url"] == f"/api/v1/tasks/{payload['task_id']}"
    assert api_client._transport.app.state.arq_redis.calls == [
        ("run_analysis_job", payload["task_id"], "https://github.com/octocat/Hello-World"),
    ]
    retry_status = await store.get_status(payload["task_id"])
    assert retry_status is not None
    assert retry_status.state is TaskState.QUEUED
