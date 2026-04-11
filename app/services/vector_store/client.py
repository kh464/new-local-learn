from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, object]


@dataclass(frozen=True)
class VectorSearchHit:
    id: str
    score: float
    payload: dict[str, object]


class BaseVectorStore:
    async def ensure_collection(self, *, name: str, dimension: int) -> None:
        raise NotImplementedError

    async def upsert(self, *, collection: str, points: list[VectorPoint]) -> None:
        raise NotImplementedError

    async def search(
        self,
        *,
        collection: str,
        vector: list[float],
        limit: int = 10,
        filters: dict[str, object] | None = None,
    ) -> list[VectorSearchHit]:
        raise NotImplementedError

    async def delete_by_filter(self, *, collection: str, filters: dict[str, object]) -> None:
        raise NotImplementedError

    async def healthcheck(self) -> bool:
        raise NotImplementedError

