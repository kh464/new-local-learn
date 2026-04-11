from __future__ import annotations

import httpx

from app.services.vector_store.client import BaseVectorStore, VectorPoint, VectorSearchHit


class QdrantVectorStore(BaseVectorStore):
    def __init__(
        self,
        *,
        url: str,
        api_key: str | None = None,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._transport = transport

    async def ensure_collection(self, *, name: str, dimension: int) -> None:
        payload = {
            "vectors": {
                "size": dimension,
                "distance": "Cosine",
            }
        }
        await self._request("PUT", f"/collections/{name}", json=payload)

    async def upsert(self, *, collection: str, points: list[VectorPoint]) -> None:
        payload = {
            "points": [
                {
                    "id": point.id,
                    "vector": point.vector,
                    "payload": point.payload,
                }
                for point in points
            ]
        }
        await self._request("PUT", f"/collections/{collection}/points", json=payload)

    async def search(
        self,
        *,
        collection: str,
        vector: list[float],
        limit: int = 10,
        filters: dict[str, object] | None = None,
    ) -> list[VectorSearchHit]:
        payload: dict[str, object] = {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
        }
        if filters:
            payload["filter"] = self._build_filter(filters)
        response = await self._request("POST", f"/collections/{collection}/points/search", json=payload)
        data = response.json()
        results = data.get("result") or []
        return [
            VectorSearchHit(
                id=str(item["id"]),
                score=float(item["score"]),
                payload=dict(item.get("payload") or {}),
            )
            for item in results
        ]

    async def delete_by_filter(self, *, collection: str, filters: dict[str, object]) -> None:
        payload = {"filter": self._build_filter(filters)}
        await self._request("POST", f"/collections/{collection}/points/delete", json=payload)

    async def healthcheck(self) -> bool:
        response = await self._request("GET", "/")
        return response.status_code < 400

    def _build_filter(self, filters: dict[str, object]) -> dict[str, object]:
        return {
            "must": [
                {
                    "key": key,
                    "match": {"value": value},
                }
                for key, value in filters.items()
            ]
        }

    async def _request(self, method: str, path: str, *, json: dict[str, object] | None = None) -> httpx.Response:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["api-key"] = self._api_key
        async with httpx.AsyncClient(base_url=self._url, timeout=self._timeout, transport=self._transport) as client:
            response = await client.request(method, path, headers=headers, json=json)
            response.raise_for_status()
            return response

