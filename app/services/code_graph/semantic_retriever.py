from __future__ import annotations

from app.services.code_graph.models import RetrievalCandidate
from app.services.vector_store.client import BaseVectorStore


class SemanticRetriever:
    def __init__(
        self,
        *,
        embedding_client,
        vector_store: BaseVectorStore,
        collection_name: str = "repo_semantic_items",
        embedding_model: str,
    ) -> None:
        self._embedding_client = embedding_client
        self._vector_store = vector_store
        self._collection_name = collection_name
        self._embedding_model = embedding_model

    async def retrieve(
        self,
        *,
        task_id: str,
        question: str,
        item_types: list[str] | None = None,
        language: str | None = None,
        limit: int = 12,
    ) -> list[RetrievalCandidate]:
        embeddings = await self._embedding_client.embed_texts([question], model=self._embedding_model)
        filters: dict[str, object] = {"task_id": task_id}
        if language:
            filters["language"] = language
        if item_types and len(item_types) == 1:
            filters["item_type"] = item_types[0]
        hits = await self._vector_store.search(
            collection=self._collection_name,
            vector=list(embeddings[0]),
            limit=limit,
            filters=filters,
        )
        return [
            RetrievalCandidate(
                task_id=str(hit.payload.get("task_id") or task_id),
                item_id=str(hit.payload.get("item_id") or hit.id),
                item_type=str(hit.payload.get("item_type") or "symbol"),
                path=str(hit.payload.get("path")) if hit.payload.get("path") is not None else None,
                symbol_id=str(hit.payload.get("item_id")) if hit.payload.get("item_type") == "symbol" else None,
                qualified_name=str(hit.payload.get("qualified_name")) if hit.payload.get("qualified_name") is not None else None,
                score=float(hit.score),
                source="semantic",
                summary_zh=str(hit.payload.get("summary_zh")) if hit.payload.get("summary_zh") is not None else None,
            )
            for hit in hits
        ]

