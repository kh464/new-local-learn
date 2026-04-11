from __future__ import annotations

import httpx

from app.services.llm.config import RuntimeConfig


class EmbeddingClient:
    def __init__(self, runtime_config: RuntimeConfig, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._runtime_config = runtime_config
        self._transport = transport

    async def embed_texts(self, texts: list[str], *, model: str) -> list[list[float]]:
        payload = {
            "model": model,
            "input": texts,
        }
        headers = {"Authorization": f"Bearer {self._runtime_config.provider.api_key.get_secret_value()}"}

        last_error: Exception | None = None
        async with httpx.AsyncClient(
            base_url=self._runtime_config.provider.base_url.rstrip("/"),
            timeout=self._runtime_config.timeout_seconds,
            transport=self._transport,
        ) as client:
            for _ in range(self._runtime_config.max_retries + 1):
                try:
                    response = await client.post("/embeddings", headers=headers, json=payload)
                    response.raise_for_status()
                    return _extract_embeddings(response.json())
                except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                    last_error = exc
        raise RuntimeError("Embedding request failed.") from last_error


def _extract_embeddings(payload: dict[str, object]) -> list[list[float]]:
    items = payload.get("data")
    if not isinstance(items, list):
        raise ValueError("Embedding response does not contain data.")
    vectors: list[list[float]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Embedding response item must be an object.")
        embedding = item.get("embedding")
        if not isinstance(embedding, list):
            raise ValueError("Embedding response item does not contain a vector.")
        vectors.append([float(value) for value in embedding])
    return vectors
