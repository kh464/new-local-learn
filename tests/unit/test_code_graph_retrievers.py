from __future__ import annotations

import pytest

from app.services.code_graph.hybrid_ranker import HybridRanker
from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode, RetrievalCandidate
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


def test_hybrid_ranker_prioritizes_must_include_entities_for_init_state_questions():
    ranker = HybridRanker()
    merged = ranker.rank(
        exact_hits=[
            RetrievalCandidate(
                task_id="task-1",
                item_id="function:python:app/main.py:app.main.create_app",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.create_app",
                qualified_name="app.main.create_app",
                score=120.0,
                source="exact",
                summary_zh="应用初始化入口。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="function:python:app/runtime.py:app.runtime.build_runtime_state",
                item_type="symbol",
                path="app/runtime.py",
                symbol_id="function:python:app/runtime.py:app.runtime.build_runtime_state",
                qualified_name="app.runtime.build_runtime_state",
                score=126.0,
                source="exact",
                summary_zh="运行时状态初始化。",
            ),
        ],
        semantic_hits=[],
        question_type="init_state_explanation",
        search_queries=["create_app", "app.state"],
        must_include_entities=["create_app", "app.state"],
        preferred_evidence_kinds=["state_assignment_fact", "symbol"],
        limit=5,
    )

    assert merged[0].qualified_name == "app.main.create_app"


def test_hybrid_ranker_prioritizes_route_evidence_for_api_inventory_questions():
    ranker = HybridRanker()
    merged = ranker.rank(
        exact_hits=[
            RetrievalCandidate(
                task_id="task-1",
                item_id="route:python:app/main.py:app.main.create_app.health.__route__.app.get:/health",
                item_type="symbol",
                path="app/main.py",
                symbol_id="route:python:app/main.py:app.main.create_app.health.__route__.app.get:/health",
                qualified_name="app.main.create_app.health.__route__.app.get:/health",
                score=120.0,
                source="exact",
                summary_zh="健康检查路由。",
            ),
            RetrievalCandidate(
                task_id="task-1",
                item_id="function:python:app/main.py:app.main.create_app.health",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.create_app.health",
                qualified_name="app.main.create_app.health",
                score=128.0,
                source="exact",
                summary_zh="健康检查处理函数。",
            ),
        ],
        semantic_hits=[],
        question_type="api_inventory",
        search_queries=["/health", "health"],
        must_include_entities=[],
        preferred_evidence_kinds=["health_fact", "route_fact", "symbol"],
        limit=5,
    )

    assert merged[0].item_id.startswith("route:")


def test_exact_retriever_builds_planning_context_from_summary_and_entry_hints(tmp_path):
    db_path = tmp_path / "knowledge.db"
    graph_store = CodeGraphStore(db_path)
    graph_store.initialize()
    graph_store.upsert_files(
        [
            CodeFileNode(
                task_id="task-ctx",
                path="app/main.py",
                language="python",
                file_kind="source",
                summary_zh="应用启动入口与依赖挂载。",
                entry_role="backend_entry",
            ),
            CodeFileNode(
                task_id="task-ctx",
                path="app/services/knowledge/retriever.py",
                language="python",
                file_kind="source",
                summary_zh="负责仓库知识库检索与证据组装。",
            ),
        ]
    )
    graph_store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-ctx",
                symbol_id="class:python:app/services/knowledge/retriever.py:app.services.knowledge.retriever.KnowledgeRetriever",
                symbol_kind="class",
                name="KnowledgeRetriever",
                qualified_name="app.services.knowledge.retriever.KnowledgeRetriever",
                file_path="app/services/knowledge/retriever.py",
                start_line=1,
                end_line=40,
                summary_zh="知识库检索器，负责聚合代码证据。",
                language="python",
            )
        ]
    )

    retriever = ExactRetriever(graph_store=graph_store, chunk_retriever=_FakeChunkRetriever())
    context = retriever.build_planning_context(
        task_id="task-ctx",
        question="这个仓库是否具有知识库能力？",
        limit=4,
    )

    assert context["file_hints"]
    assert context["symbol_hints"]
    assert any(item["path"] == "app/services/knowledge/retriever.py" for item in context["file_hints"])
    assert any(
        item["qualified_name"] == "app.services.knowledge.retriever.KnowledgeRetriever"
        for item in context["symbol_hints"]
    )


def test_exact_retriever_builds_relation_hints_for_architecture_questions(tmp_path):
    db_path = tmp_path / "knowledge.db"
    graph_store = CodeGraphStore(db_path)
    graph_store.initialize()
    graph_store.upsert_files(
        [
            CodeFileNode(
                task_id="task-rel",
                path="app/main.py",
                language="python",
                file_kind="source",
                summary_zh="任务提交入口。",
                entry_role="backend_entry",
                keywords_zh=["任务提交", "分析任务"],
            ),
            CodeFileNode(
                task_id="task-rel",
                path="app/task_queue.py",
                language="python",
                file_kind="source",
                summary_zh="任务队列实现。",
                keywords_zh=["任务队列", "提交任务"],
            ),
        ]
    )
    graph_store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-rel",
                symbol_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                symbol_kind="function",
                name="enqueue_turn_task",
                qualified_name="app.main.create_app.enqueue_turn_task",
                file_path="app/main.py",
                start_line=10,
                end_line=20,
                summary_zh="分析任务提交入口。",
                language="python",
            ),
            CodeSymbolNode(
                task_id="task-rel",
                symbol_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                symbol_kind="method",
                name="submit",
                qualified_name="app.task_queue.InMemoryTaskQueue.submit",
                file_path="app/task_queue.py",
                start_line=30,
                end_line=60,
                summary_zh="任务入队方法。",
                language="python",
            ),
        ]
    )
    graph_store.insert_edges(
        [
            CodeEdge(
                task_id="task-rel",
                from_symbol_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                to_symbol_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                edge_kind="calls",
                source_path="app/main.py",
                line=15,
            )
        ]
    )

    retriever = ExactRetriever(graph_store=graph_store, chunk_retriever=_FakeChunkRetriever())
    context = retriever.build_planning_context(
        task_id="task-rel",
        question="用户提交分析任务后主链路是什么？",
        limit=4,
    )

    assert context["relation_hints"]
    assert context["keyword_hints"]
    assert context["relation_hints"][0]["from_qualified_name"] == "app.main.create_app.enqueue_turn_task"
    assert context["relation_hints"][0]["to_qualified_name"] == "app.task_queue.InMemoryTaskQueue.submit"
    assert "任务队列" in context["keyword_hints"]
