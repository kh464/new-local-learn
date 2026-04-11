from __future__ import annotations

import pytest

from app.services.code_graph.embedding_indexer import EmbeddingIndexer
from app.services.code_graph.models import CodeFileNode, CodeSymbolNode
from app.services.code_graph.storage import CodeGraphStore


class _FakeEmbeddingClient:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str], *, model: str) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(index + 1), 0.5, 0.25] for index, _ in enumerate(texts)]


class _FakeVectorStore:
    def __init__(self) -> None:
        self.collections: list[tuple[str, int]] = []
        self.upserts: list[tuple[str, list[object]]] = []

    async def ensure_collection(self, *, name: str, dimension: int) -> None:
        self.collections.append((name, dimension))

    async def upsert(self, *, collection: str, points: list[object]) -> None:
        self.upserts.append((collection, points))

    async def search(self, *, collection: str, vector: list[float], limit: int = 10, filters=None):
        raise NotImplementedError

    async def delete_by_filter(self, *, collection: str, filters):
        raise NotImplementedError

    async def healthcheck(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_embedding_indexer_indexes_graph_records_and_registers_registry(tmp_path):
    db_path = tmp_path / "knowledge.db"
    graph_store = CodeGraphStore(db_path)
    graph_store.initialize()
    graph_store.upsert_files(
        [
            CodeFileNode(
                task_id="task-1",
                path="app/main.py",
                language="python",
                file_kind="source",
                summary_zh="该文件负责定义应用入口。",
                entry_role="backend_entry",
            )
        ]
    )
    graph_store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/main.py:app.main.health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=1,
                end_line=4,
                summary_zh="该函数负责健康检查。",
                language="python",
            )
        ]
    )

    embedding_client = _FakeEmbeddingClient()
    vector_store = _FakeVectorStore()
    indexer = EmbeddingIndexer(
        embedding_client=embedding_client,
        vector_store=vector_store,
        graph_store=graph_store,
        collection_name="repo_semantic_items",
        embedding_model="demo-embed",
    )

    count = await indexer.index_task_records(task_id="task-1")
    registry_rows = graph_store.list_embedding_registry(task_id="task-1")

    assert count == 2
    assert vector_store.collections == [("repo_semantic_items", 3)]
    assert len(vector_store.upserts) == 1
    assert len(vector_store.upserts[0][1]) == 2
    assert len(registry_rows) == 2
    assert {row["item_ref_id"] for row in registry_rows} == {"app/main.py", "function:python:app/main.py:app.main.health"}
    assert embedding_client.calls[0][0].startswith("该文件负责")

