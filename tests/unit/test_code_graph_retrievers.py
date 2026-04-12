from __future__ import annotations

import pytest

from app.services.code_graph.hybrid_ranker import HybridRanker
from app.services.code_graph.models import CodeFileNode, CodeSymbolNode, RetrievalCandidate
from app.services.code_graph.exact_retriever import ExactRetriever
from app.services.code_graph.semantic_retriever import SemanticRetriever
from app.services.code_graph.storage import CodeGraphStore


class _FakeChunkRetriever:
    def retrieve(self, *, task_id: str, db_path, question: str, limit: int = 6):
        return []


class _FakeEmbeddingClient:
    async def embed_texts(self, texts: list[str], *, model: str) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeVectorStore:
    async def search(self, *, collection: str, vector: list[float], limit: int = 10, filters=None):
        return [
            type(
                "Hit",
                (),
                {
                    "id": "point-1",
                    "score": 0.88,
                    "payload": {
                        "task_id": "task-1",
                        "item_id": "function:python:app/main.py:app.main.health",
                        "item_type": "symbol",
                        "path": "app/main.py",
                        "qualified_name": "app.main.health",
                        "summary_zh": "该函数负责健康检查。",
                    },
                },
            )()
        ]


def test_exact_retriever_prefers_symbol_and_file_matches(tmp_path):
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
                summary_zh="该文件负责应用入口。",
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

    retriever = ExactRetriever(graph_store=graph_store, chunk_retriever=_FakeChunkRetriever())
    hits = retriever.retrieve(
        task_id="task-1",
        db_path=db_path,
        question="请解释 app.main.health 的作用",
        normalized_question="解释 app.main.health 的作用",
        target_entities=["app.main.health"],
        limit=5,
    )

    assert hits
    assert hits[0].qualified_name == "app.main.health"
    assert hits[0].source == "exact"


def test_exact_retriever_can_match_chinese_summary_queries(tmp_path):
    db_path = tmp_path / "knowledge.db"
    graph_store = CodeGraphStore(db_path)
    graph_store.initialize()
    graph_store.upsert_files(
        [
            CodeFileNode(
                task_id="task-1",
                path="app/services/knowledge/retriever.py",
                language="python",
                file_kind="source",
                summary_zh="该文件负责仓库知识库检索与证据组装。",
                entry_role=None,
            )
        ]
    )

    retriever = ExactRetriever(graph_store=graph_store, chunk_retriever=_FakeChunkRetriever())
    hits = retriever.retrieve(
        task_id="task-1",
        db_path=db_path,
        question="仓库是否具有知识库？",
        normalized_question="确认仓库是否实现知识库能力",
        target_entities=[],
        search_queries=["知识库", "检索"],
        limit=5,
    )

    assert hits
    assert hits[0].path == "app/services/knowledge/retriever.py"
    assert hits[0].source == "exact"


def test_exact_retriever_uses_search_queries_for_direct_symbol_and_path_matches(tmp_path):
    db_path = tmp_path / "knowledge.db"
    graph_store = CodeGraphStore(db_path)
    graph_store.initialize()
    graph_store.upsert_files(
        [
            CodeFileNode(
                task_id="task-1",
                path="app/tasks/jobs.py",
                language="python",
                file_kind="source",
                summary_zh="该文件负责后台任务执行流程。",
                entry_role=None,
            )
        ]
    )
    graph_store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/tasks/jobs.py:app.tasks.jobs.run_analysis_job",
                symbol_kind="function",
                name="run_analysis_job",
                qualified_name="app.tasks.jobs.run_analysis_job",
                file_path="app/tasks/jobs.py",
                start_line=1,
                end_line=20,
                summary_zh="该函数负责执行分析任务主流程。",
                language="python",
            )
        ]
    )

    retriever = ExactRetriever(graph_store=graph_store, chunk_retriever=_FakeChunkRetriever())
    hits = retriever.retrieve(
        task_id="task-1",
        db_path=db_path,
        question="用户提交分析任务后后端会经过哪些步骤",
        normalized_question="说明分析任务后端执行流程",
        target_entities=[],
        search_queries=["run_analysis_job", "app/tasks/jobs.py"],
        limit=5,
    )

    assert hits
    assert any(hit.qualified_name == "app.tasks.jobs.run_analysis_job" for hit in hits)
    assert any(hit.path == "app/tasks/jobs.py" for hit in hits)


@pytest.mark.asyncio
async def test_semantic_retriever_returns_candidates_from_vector_hits():
    retriever = SemanticRetriever(
        embedding_client=_FakeEmbeddingClient(),
        vector_store=_FakeVectorStore(),
        collection_name="repo_semantic_items",
        embedding_model="demo-embed",
    )

    hits = await retriever.retrieve(
        task_id="task-1",
        question="健康检查在哪里实现",
        item_types=["symbol"],
        language="python",
        limit=5,
    )

    assert hits
    assert hits[0].qualified_name == "app.main.health"
    assert hits[0].source == "semantic"


def test_hybrid_ranker_merges_exact_and_semantic_hits():
    ranker = HybridRanker()
    merged = ranker.rank(
        exact_hits=[
            RetrievalCandidate(
                task_id="task-1",
                item_id="function:python:app/main.py:app.main.health",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.health",
                qualified_name="app.main.health",
                score=120.0,
                source="exact",
                summary_zh="该函数负责健康检查。",
            )
        ],
        semantic_hits=[
            RetrievalCandidate(
                task_id="task-1",
                item_id="function:python:app/main.py:app.main.health",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.health",
                qualified_name="app.main.health",
                score=0.88,
                source="semantic",
                summary_zh="该函数负责健康检查。",
            )
        ],
        limit=5,
    )

    assert len(merged) == 1
    assert merged[0].qualified_name == "app.main.health"
    assert merged[0].score > 120.0


def test_hybrid_ranker_prioritizes_execution_symbols_for_architecture_questions():
    ranker = HybridRanker()
    merged = ranker.rank(
        exact_hits=[
            RetrievalCandidate(
                task_id="task-1",
                item_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                qualified_name="app.main.create_app.enqueue_turn_task",
                score=130.0,
                source="exact",
                summary_zh="提交任务入口函数。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                item_type="symbol",
                path="app/task_queue.py",
                symbol_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                qualified_name="app.task_queue.InMemoryTaskQueue.submit",
                score=130.0,
                source="exact",
                summary_zh="任务入队方法。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="class:python:app/api/schemas.py:app.api.schemas.TurnTaskRequest",
                item_type="symbol",
                path="app/api/schemas.py",
                symbol_id="class:python:app/api/schemas.py:app.api.schemas.TurnTaskRequest",
                qualified_name="app.api.schemas.TurnTaskRequest",
                score=130.0,
                source="exact",
                summary_zh="任务提交请求结构。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="class:python:app/config.py:app.config.TaskQueueSettings",
                item_type="symbol",
                path="app/config.py",
                symbol_id="class:python:app/config.py:app.config.TaskQueueSettings",
                qualified_name="app.config.TaskQueueSettings",
                score=130.0,
                source="exact",
                summary_zh="任务队列配置。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="function:python:alembic/versions/20260407_000002_create_task_queue_table.py:alembic.versions.20260407_000002_create_task_queue_table.upgrade",
                item_type="symbol",
                path="alembic/versions/20260407_000002_create_task_queue_table.py",
                symbol_id="function:python:alembic/versions/20260407_000002_create_task_queue_table.py:alembic.versions.20260407_000002_create_task_queue_table.upgrade",
                qualified_name="alembic.versions.20260407_000002_create_task_queue_table.upgrade",
                score=130.0,
                source="exact",
                summary_zh="迁移创建任务队列表。",
            ),
        ],
        semantic_hits=[],
        question_type="architecture_explanation",
        search_queries=["task_queue.py", "enqueue", "submit"],
        limit=5,
    )

    qualified_names = [item.qualified_name for item in merged if item.qualified_name]
    assert set(qualified_names[:2]) == {
        "app.main.create_app.enqueue_turn_task",
        "app.task_queue.InMemoryTaskQueue.submit",
    }


def test_hybrid_ranker_does_not_overboost_generic_methods_from_task_queue_file():
    ranker = HybridRanker()
    merged = ranker.rank(
        exact_hits=[
            RetrievalCandidate(
                task_id="task-1",
                item_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                qualified_name="app.main.create_app.enqueue_turn_task",
                score=130.0,
                source="exact",
                summary_zh="提交任务入口函数。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                item_type="symbol",
                path="app/task_queue.py",
                symbol_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                qualified_name="app.task_queue.InMemoryTaskQueue.submit",
                score=130.0,
                source="exact",
                summary_zh="任务入队方法。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue._worker_loop",
                item_type="symbol",
                path="app/task_queue.py",
                symbol_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue._worker_loop",
                qualified_name="app.task_queue.InMemoryTaskQueue._worker_loop",
                score=130.0,
                source="exact",
                summary_zh="任务工作循环。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.__init__",
                item_type="symbol",
                path="app/task_queue.py",
                symbol_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.__init__",
                qualified_name="app.task_queue.InMemoryTaskQueue.__init__",
                score=130.0,
                source="exact",
                summary_zh="初始化方法。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue._emit",
                item_type="symbol",
                path="app/task_queue.py",
                symbol_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue._emit",
                qualified_name="app.task_queue.InMemoryTaskQueue._emit",
                score=130.0,
                source="exact",
                summary_zh="发送更新。",
            ),
        ],
        semantic_hits=[],
        question_type="architecture_explanation",
        search_queries=["task_queue.py", "enqueue", "submit", "_worker_loop"],
        limit=5,
    )

    qualified_names = [item.qualified_name for item in merged if item.qualified_name]
    assert qualified_names[0] == "app.main.create_app.enqueue_turn_task"
    assert set(qualified_names[1:3]) == {
        "app.task_queue.InMemoryTaskQueue._worker_loop",
        "app.task_queue.InMemoryTaskQueue.submit",
    }
