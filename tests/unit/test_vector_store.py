from __future__ import annotations

import json

import httpx
import pytest

from app.services.vector_store.client import VectorPoint
from app.services.vector_store.qdrant_store import QdrantVectorStore


@pytest.mark.asyncio
async def test_qdrant_vector_store_uses_http_api_for_collection_and_search():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/collections/repo_semantic_items" and request.method == "PUT":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/collections/repo_semantic_items/points" and request.method == "PUT":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/collections/repo_semantic_items/points/search" and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "id": "point-1",
                            "score": 0.91,
                            "payload": {
                                "task_id": "task-1",
                                "item_type": "symbol",
                                "qualified_name": "app.main.health",
                            },
                        }
                    ]
                },
            )
        if request.url.path == "/collections/repo_semantic_items/points/delete" and request.method == "POST":
            return httpx.Response(200, json={"status": "ok"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    store = QdrantVectorStore(
        url="https://qdrant.test",
        api_key="secret-key",
        transport=httpx.MockTransport(handler),
    )

    await store.ensure_collection(name="repo_semantic_items", dimension=3)
    await store.upsert(
        collection="repo_semantic_items",
        points=[
            VectorPoint(
                id="point-1",
                vector=[0.1, 0.2, 0.3],
                payload={"task_id": "task-1", "item_type": "symbol"},
            )
        ],
    )
    hits = await store.search(
        collection="repo_semantic_items",
        vector=[0.1, 0.2, 0.3],
        limit=5,
        filters={"task_id": "task-1", "item_type": "symbol"},
    )
    await store.delete_by_filter(
        collection="repo_semantic_items",
        filters={"task_id": "task-1"},
    )

    assert hits[0].id == "point-1"
    assert hits[0].score == 0.91
    assert hits[0].payload["qualified_name"] == "app.main.health"
    assert requests[0].headers["api-key"] == "secret-key"
    create_payload = json.loads(requests[0].content.decode("utf-8"))
    assert create_payload["vectors"]["size"] == 3
    upsert_payload = json.loads(requests[1].content.decode("utf-8"))
    assert upsert_payload["points"][0]["id"] == "point-1"
    search_payload = json.loads(requests[2].content.decode("utf-8"))
    assert search_payload["limit"] == 5
    assert search_payload["filter"]["must"][0]["key"] == "task_id"

