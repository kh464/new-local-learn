from __future__ import annotations

import pytest

from app.services.code_graph.embedding_indexer import EmbeddingIndexer
from app.services.code_graph.models import CodeFileNode
from app.services.code_graph.storage import CodeGraphStore


@pytest.mark.asyncio
async def test_embedding_indexer_uses_richer_cognition_summary_text(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = CodeGraphStore(db_path)
    store.initialize()
    store.upsert_files(
        [
            CodeFileNode(
                task_id="task-1",
                path="app/main.py",
                language="python",
                file_kind="source",
                summary_zh="该文件负责应用入口。",
                responsibility_zh="负责 FastAPI 初始化",
                upstream_zh="由 Uvicorn 启动导入",
                downstream_zh="向路由分发请求",
                keywords_zh=["FastAPI", "入口"],
            )
        ]
    )

    captured: dict[str, object] = {}

    class FakeEmbeddingClient:
        async def embed_texts(self, texts, *, model):
            captured["texts"] = texts
            return [[0.1, 0.2, 0.3] for _ in texts]

    class FakeVectorStore:
        async def ensure_collection(self, *, name, dimension):
            return None

        async def upsert(self, *, collection, points):
            return None

        async def delete_by_filter(self, *, collection, filters):
            return None

        async def healthcheck(self) -> bool:
            return True

    indexer = EmbeddingIndexer(
        graph_store=store,
        embedding_client=FakeEmbeddingClient(),
        vector_store=FakeVectorStore(),
        collection_name="repo_semantic_items",
        embedding_model="demo-embed",
    )
    await indexer.index_task_records(task_id="task-1")

    assert "负责 FastAPI 初始化" in captured["texts"][0]
    assert "由 Uvicorn 启动导入" in captured["texts"][0]
    assert "关键词：FastAPI、入口" in captured["texts"][0]
