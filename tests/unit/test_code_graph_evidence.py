from __future__ import annotations

from app.services.code_graph.code_locator import CodeLocator
from app.services.code_graph.evidence_builder import GraphEvidenceBuilder
from app.services.code_graph.graph_expander import GraphExpander
from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSymbolNode, RetrievalCandidate
from app.services.code_graph.pipeline import CodeGraphBuildPipeline
from app.services.code_graph.storage import CodeGraphStore


def test_graph_expander_and_code_locator_build_local_subgraph_and_snippets(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "app").mkdir(parents=True)
    source_path = repo_root / "app" / "main.py"
    source_path.write_text(
        "def helper():\n"
        "    return {'ok': True}\n\n"
        "def health():\n"
        "    return helper()\n",
        encoding="utf-8",
    )

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
                summary_zh="该文件负责应用入口与健康检查。",
                entry_role="backend_entry",
            )
        ]
    )
    graph_store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/main.py:app.main.helper",
                symbol_kind="function",
                name="helper",
                qualified_name="app.main.helper",
                file_path="app/main.py",
                start_line=1,
                end_line=2,
                summary_zh="该函数返回健康检查结果。",
                language="python",
            ),
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/main.py:app.main.health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=4,
                end_line=5,
                summary_zh="该函数负责健康检查入口。",
                language="python",
            ),
        ]
    )
    graph_store.insert_edges(
        [
            CodeEdge(
                task_id="task-1",
                from_symbol_id="file:python:app/main.py",
                to_symbol_id="function:python:app/main.py:app.main.health",
                edge_kind="contains",
                source_path="app/main.py",
                line=4,
            ),
            CodeEdge(
                task_id="task-1",
                from_symbol_id="file:python:app/main.py",
                to_symbol_id="function:python:app/main.py:app.main.helper",
                edge_kind="contains",
                source_path="app/main.py",
                line=1,
            ),
            CodeEdge(
                task_id="task-1",
                from_symbol_id="function:python:app/main.py:app.main.health",
                to_symbol_id="function:python:app/main.py:app.main.helper",
                edge_kind="calls",
                source_path="app/main.py",
                line=5,
            ),
        ]
    )

    seeds = [
        RetrievalCandidate(
            task_id="task-1",
            item_id="function:python:app/main.py:app.main.health",
            item_type="symbol",
            path="app/main.py",
            symbol_id="function:python:app/main.py:app.main.health",
            qualified_name="app.main.health",
            score=120.0,
            source="exact",
            summary_zh="该函数负责健康检查入口。",
        )
    ]

    subgraph = GraphExpander(graph_store=graph_store).expand(task_id="task-1", seeds=seeds, max_hops=2, max_nodes=10)
    snippets = CodeLocator(repo_root=repo_root).locate(subgraph=subgraph)
    evidence = GraphEvidenceBuilder().build(
        question="health 做了什么",
        normalized_question="解释 health 的职责",
        retrieval_objective="定位 health 函数和它的下游调用",
        subgraph=subgraph,
        snippets=snippets,
    )

    assert any(symbol.qualified_name == "app.main.health" for symbol in subgraph.symbols)
    assert any(symbol.qualified_name == "app.main.helper" for symbol in subgraph.symbols)
    assert any(edge.edge_kind == "calls" for edge in subgraph.edges)
    assert snippets
    assert "def health" in snippets[0].snippet or "def helper" in snippets[0].snippet
    assert evidence.graph_nodes
    assert evidence.snippets


def test_graph_expander_bridges_unresolved_attribute_calls_into_matching_symbols(tmp_path):
    repo_root = tmp_path / "repo"
    (repo_root / "app").mkdir(parents=True)
    (repo_root / "app" / "main.py").write_text(
        "from app.task_queue import InMemoryTaskQueue\n\n"
        "def create_app():\n"
        "    task_queue = InMemoryTaskQueue()\n\n"
        "    def enqueue_turn_task():\n"
        "        return task_queue.submit(task_type='turn', session_id='s', owner_id='o')\n\n"
        "    return enqueue_turn_task\n",
        encoding="utf-8",
    )
    (repo_root / "app" / "task_queue.py").write_text(
        "class InMemoryTaskQueue:\n"
        "    def submit(self, task_type, session_id, owner_id):\n"
        "        return {'task_type': task_type, 'session_id': session_id, 'owner_id': owner_id}\n\n"
        "    def _worker_loop(self):\n"
        "        return self._execute()\n\n"
        "    def _execute(self):\n"
        "        return {'status': 'completed'}\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "knowledge.db"
    CodeGraphBuildPipeline().build(task_id="task-unresolved", repo_root=repo_root, db_path=db_path)
    graph_store = CodeGraphStore(db_path)

    enqueue_symbol = next(
        symbol
        for symbol in graph_store.list_symbols(task_id="task-unresolved")
        if symbol.qualified_name.endswith("create_app.enqueue_turn_task")
    )
    seeds = [
        RetrievalCandidate(
            task_id="task-unresolved",
            item_id=enqueue_symbol.symbol_id,
            item_type="symbol",
            path=enqueue_symbol.file_path,
            symbol_id=enqueue_symbol.symbol_id,
            qualified_name=enqueue_symbol.qualified_name,
            score=120.0,
            source="exact",
            summary_zh=enqueue_symbol.summary_zh,
        )
    ]

    subgraph = GraphExpander(graph_store=graph_store).expand(
        task_id="task-unresolved",
        seeds=seeds,
        max_hops=3,
        max_nodes=20,
    )

    assert any(symbol.qualified_name == "app.task_queue.InMemoryTaskQueue.submit" for symbol in subgraph.symbols)
    assert any(symbol.qualified_name == "app.task_queue.InMemoryTaskQueue._worker_loop" for symbol in subgraph.symbols)
    assert any(file.path == "app/task_queue.py" for file in subgraph.files)
    assert any(
        edge.edge_kind == "calls"
        and edge.from_symbol_id == enqueue_symbol.symbol_id
        and edge.to_symbol_id.endswith("app.task_queue.InMemoryTaskQueue.submit")
        for edge in subgraph.edges
    )
