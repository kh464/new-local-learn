import pytest
from pydantic import ValidationError

from app.core.models import AnswerDebug, TaskChatCitation, TaskChatMessage, TaskState, TaskStatus
from app.storage.task_store import RedisTaskStore


async def test_task_store_round_trip(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-1", state=TaskState.QUEUED))
    loaded = await store.get_status("task-1")
    assert loaded is not None
    assert loaded.state is TaskState.QUEUED


async def test_task_store_applies_ttl_to_task_records(fakeredis_client, sample_analysis_result):
    store = RedisTaskStore(fakeredis_client, ttl_seconds=120)

    await store.set_status(TaskStatus(task_id="task-ttl", state=TaskState.QUEUED))
    await store.set_result("task-ttl", sample_analysis_result)
    await store.append_event("task-ttl", {"stage": "queued"})

    assert await fakeredis_client.ttl(store._status_key("task-ttl")) > 0
    assert await fakeredis_client.ttl(store._result_key("task-ttl")) > 0
    assert await fakeredis_client.ttl(store._events_key("task-ttl")) > 0


async def test_task_store_result_and_events(fakeredis_client, sample_analysis_result):
    store = RedisTaskStore(fakeredis_client)
    await store.set_result("task-2", sample_analysis_result)
    result = await store.get_result("task-2")
    assert result == sample_analysis_result

    await fakeredis_client.set(store._result_key("task-3"), '{"doc":"ready"}')
    with pytest.raises(ValidationError):
        await store.get_result("task-3")

    await store.append_event("task-2", {"stage": "fetch_repo"})
    await store.append_event("task-2", {"stage": "scan_tree"})
    events = await store.get_events("task-2")
    assert events == [{"stage": "fetch_repo"}, {"stage": "scan_tree"}]


async def test_task_store_access_tokens_round_trip(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_task_access_token("task-7", "token-7")

    assert await store.has_task_access_token("task-7", "token-7") is True
    assert await store.has_task_access_token("task-7", "wrong-token") is False


async def test_task_store_delete_task_removes_all_records(fakeredis_client, sample_analysis_result):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-3", state=TaskState.QUEUED))
    await store.set_result("task-3", sample_analysis_result)
    await store.append_event("task-3", {"stage": "fetch_repo"})

    await store.delete_task("task-3")

    assert await store.get_status("task-3") is None
    assert await store.get_result("task-3") is None
    assert await store.get_events("task-3") == []


async def test_task_store_rate_limit_window(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)

    first = await store.hit_rate_limit("analyze:127.0.0.1", limit=2, window_seconds=60)
    second = await store.hit_rate_limit("analyze:127.0.0.1", limit=2, window_seconds=60)
    third = await store.hit_rate_limit("analyze:127.0.0.1", limit=2, window_seconds=60)

    assert first == {"allowed": True, "limit": 2, "remaining": 1, "retry_after": 60}
    assert second == {"allowed": True, "limit": 2, "remaining": 0, "retry_after": 60}
    assert third == {"allowed": False, "limit": 2, "remaining": 0, "retry_after": 60}


async def test_task_store_metrics_snapshot(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)

    await store.increment_metric("analyze_requests_total")
    await store.increment_metric("analyze_requests_total", amount=2)
    await store.increment_metric("analysis_jobs_succeeded_total")

    snapshot = await store.get_metrics_snapshot()

    assert snapshot["analyze_requests_total"] == 3
    assert snapshot["analysis_jobs_succeeded_total"] == 1


async def test_task_store_audit_events_round_trip_and_limit(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)

    await store.append_audit_event({"action": "first", "outcome": "accepted"})
    await store.append_audit_event({"action": "second", "outcome": "denied"})

    latest = await store.get_audit_events(limit=1)
    all_events = await store.get_audit_events(limit=10)

    assert latest == {
        "events": [{"action": "second", "outcome": "denied"}],
        "total": 2,
        "limit": 1,
        "offset": 0,
    }
    assert all_events == {
        "events": [
            {"action": "second", "outcome": "denied"},
            {"action": "first", "outcome": "accepted"},
        ],
        "total": 2,
        "limit": 10,
        "offset": 0,
    }


async def test_task_store_audit_events_support_filters_and_offsets(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)

    await store.append_audit_event(
        {"action": "deploy", "outcome": "accepted", "task_id": "task-1", "subject": "worker"}
    )
    await store.append_audit_event(
        {"action": "deploy", "outcome": "denied", "task_id": "task-2", "subject": "worker"}
    )
    await store.append_audit_event(
        {"action": "analyze_submit", "outcome": "accepted", "task_id": "task-3", "subject": "api"}
    )

    page = await store.get_audit_events(
        limit=1,
        offset=1,
        filters={"action": "deploy", "subject": "worker"},
    )

    assert page == {
        "events": [
            {"action": "deploy", "outcome": "accepted", "task_id": "task-1", "subject": "worker"}
        ],
        "total": 2,
        "limit": 1,
        "offset": 1,
    }


async def test_task_store_task_request_and_cancel_flags_round_trip(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)

    await store.set_task_request("task-control", {"github_url": "https://github.com/octocat/Hello-World"})
    await store.request_task_cancel("task-control")

    assert await store.get_task_request("task-control") == {"github_url": "https://github.com/octocat/Hello-World"}
    assert await store.is_task_cancel_requested("task-control") is True


async def test_task_store_lists_recent_tasks_with_filters(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.set_status(TaskStatus(task_id="task-1", state=TaskState.SUCCEEDED, progress=100))
    await store.set_task_request("task-1", {"github_url": "https://github.com/octocat/one"})
    await store.set_status(TaskStatus(task_id="task-2", state=TaskState.RUNNING, progress=50))
    await store.set_task_request("task-2", {"github_url": "https://github.com/octocat/two"})

    page = await store.list_tasks(limit=1, offset=0, state=TaskState.RUNNING)

    assert page.total == 1
    assert page.limit == 1
    assert page.offset == 0
    assert len(page.tasks) == 1
    assert page.tasks[0].task_id == "task-2"
    assert page.tasks[0].github_url == "https://github.com/octocat/two"


async def test_task_store_chat_messages_round_trip(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.append_chat_message(
        "task-chat-1",
        TaskChatMessage(
            message_id="user-1",
            role="user",
            content="这个仓库的后端入口在哪？",
        ),
    )
    await store.append_chat_message(
        "task-chat-1",
        TaskChatMessage(
            message_id="assistant-1",
            role="assistant",
            content="后端入口在 app/main.py。",
            citations=[
                TaskChatCitation(
                    path="app/main.py",
                    start_line=1,
                    end_line=8,
                    reason="这里定义了 FastAPI 应用实例和路由。",
                    snippet="from fastapi import FastAPI",
                )
            ],
        ),
    )

    messages = await store.get_chat_messages("task-chat-1")

    assert [message.message_id for message in messages] == ["user-1", "assistant-1"]
    assert messages[1].citations[0].path == "app/main.py"


async def test_task_store_chat_messages_preserve_answer_debug(fakeredis_client):
    store = RedisTaskStore(fakeredis_client)
    await store.append_chat_message(
        "task-chat-debug",
        TaskChatMessage(
            message_id="assistant-debug-1",
            role="assistant",
            content="根据当前证据，后端入口在 app/main.py。",
            answer_debug=AnswerDebug(
                confirmed_facts=["已确认 app/main.py 是后端入口"],
                evidence_gaps=["尚未定位更深层调用链"],
                validation_issues=["missing_must_include_entity"],
                retry_attempted=True,
                retry_succeeded=True,
                answer_attempts=2,
                related_node_ids=["function:python:app/main.py:app.main.health"],
            ),
        ),
    )

    messages = await store.get_chat_messages("task-chat-debug")

    assert messages[0].answer_debug is not None
    assert messages[0].answer_debug.confirmed_facts == ["已确认 app/main.py 是后端入口"]
    assert messages[0].answer_debug.evidence_gaps == ["尚未定位更深层调用链"]
    assert messages[0].answer_debug.validation_issues == ["missing_must_include_entity"]
    assert messages[0].answer_debug.retry_attempted is True
    assert messages[0].answer_debug.retry_succeeded is True
    assert messages[0].answer_debug.answer_attempts == 2
    assert messages[0].answer_debug.related_node_ids == ["function:python:app/main.py:app.main.health"]
