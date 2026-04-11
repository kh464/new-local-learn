# Hybrid RAG S1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the storage and graph-foundation layer for the repository hybrid-RAG architecture without breaking the existing knowledge index or task pipeline.

**Architecture:** Extend the existing SQLite knowledge database with code graph tables, keep existing chunk indexing intact, and add a focused `CodeGraphStore` abstraction for graph records. Deliver the work in test-first slices so the new schema and CRUD behavior are validated before later AST extraction and vector indexing work lands.

**Tech Stack:** Python, SQLite/FTS5, pytest

---

### Task 1: Add failing tests for the expanded SQLite schema

**Files:**
- Modify: `tests/unit/test_knowledge_store.py`

- [ ] **Step 1: Write the failing test**

```python
def test_sqlite_knowledge_store_initializes_code_graph_tables(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = SQLiteKnowledgeStore(db_path)

    store.initialize()

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    object_names = {row[0] for row in rows}
    assert "code_file" in object_names
    assert "code_symbol" in object_names
    assert "code_edge" in object_names
    assert "code_unresolved_call" in object_names
    assert "embedding_registry" in object_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_knowledge_store.py::test_sqlite_knowledge_store_initializes_code_graph_tables -v`
Expected: FAIL because the schema does not create the new graph tables yet.

- [ ] **Step 3: Write minimal implementation**

```python
connection.executescript(
    """
    CREATE TABLE IF NOT EXISTS code_file (...);
    CREATE TABLE IF NOT EXISTS code_symbol (...);
    CREATE TABLE IF NOT EXISTS code_edge (...);
    CREATE TABLE IF NOT EXISTS code_unresolved_call (...);
    CREATE TABLE IF NOT EXISTS embedding_registry (...);
    """
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_knowledge_store.py::test_sqlite_knowledge_store_initializes_code_graph_tables -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_knowledge_store.py app/storage/knowledge_store.py
git commit -m "feat: add code graph sqlite schema"
```

### Task 2: Add failing tests for code graph storage CRUD

**Files:**
- Create: `app/services/code_graph/models.py`
- Create: `app/services/code_graph/storage.py`
- Create: `tests/unit/test_code_graph_store.py`

- [ ] **Step 1: Write the failing test**

```python
def test_code_graph_store_persists_files_symbols_edges_and_summaries(tmp_path):
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
                summary_zh="",
                entry_role="backend_entry",
            )
        ]
    )
    graph_store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="method:python:app/main.py:health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=1,
                end_line=4,
                summary_zh="",
                language="python",
            )
        ]
    )
    graph_store.insert_edges(
        [
            CodeEdge(
                task_id="task-1",
                from_symbol_id="method:python:app/main.py:health",
                to_symbol_id="method:python:app/main.py:health",
                edge_kind="contains",
                source_path="app/main.py",
                line=1,
            )
        ]
    )
    graph_store.update_file_summary(
        task_id="task-1",
        path="app/main.py",
        summary_zh="该文件负责定义 FastAPI 应用入口。",
    )
    graph_store.update_symbol_summary(
        task_id="task-1",
        symbol_id="method:python:app/main.py:health",
        summary_zh="该函数负责暴露健康检查接口。",
    )

    files = graph_store.list_files(task_id="task-1")
    symbols = graph_store.list_symbols(task_id="task-1")
    edges = graph_store.list_out_edges(
        task_id="task-1",
        symbol_id="method:python:app/main.py:health",
    )

    assert files[0].summary_zh == "该文件负责定义 FastAPI 应用入口。"
    assert symbols[0].summary_zh == "该函数负责暴露健康检查接口。"
    assert edges[0].edge_kind == "contains"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_code_graph_store.py::test_code_graph_store_persists_files_symbols_edges_and_summaries -v`
Expected: FAIL because `CodeGraphStore` and graph record models do not exist yet.

- [ ] **Step 3: Write minimal implementation**

```python
@dataclass(frozen=True)
class CodeFileNode:
    task_id: str
    path: str
    language: str
    file_kind: str
    summary_zh: str = ""
    entry_role: str | None = None


class CodeGraphStore:
    def upsert_files(self, files: list[CodeFileNode]) -> None: ...
    def upsert_symbols(self, symbols: list[CodeSymbolNode]) -> None: ...
    def insert_edges(self, edges: list[CodeEdge]) -> None: ...
    def update_file_summary(self, *, task_id: str, path: str, summary_zh: str) -> None: ...
    def update_symbol_summary(self, *, task_id: str, symbol_id: str, summary_zh: str) -> None: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_code_graph_store.py::test_code_graph_store_persists_files_symbols_edges_and_summaries -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/code_graph/models.py app/services/code_graph/storage.py tests/unit/test_code_graph_store.py
git commit -m "feat: add code graph storage primitives"
```

### Task 3: Add failing tests for FTS and embedding registry behavior

**Files:**
- Modify: `tests/unit/test_code_graph_store.py`
- Modify: `app/services/code_graph/storage.py`

- [ ] **Step 1: Write the failing test**

```python
def test_code_graph_store_searches_fts_and_registers_embeddings(tmp_path):
    db_path = tmp_path / "knowledge.db"
    graph_store = CodeGraphStore(db_path)
    graph_store.initialize()
    # seed file and symbol data here

    graph_store.register_embedding(
        task_id="task-1",
        item_type="symbol",
        item_ref_id="method:python:app/main.py:health",
        vector_store="qdrant",
        collection_name="repo_semantic_items",
        vector_point_id="point-1",
        embedding_model="test-embed",
        content_hash="abc123",
        status="ready",
    )

    symbol_hits = graph_store.search_symbols_fts(
        task_id="task-1",
        query="健康检查 FastAPI",
        limit=5,
    )

    assert symbol_hits[0].qualified_name == "app.main.health"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_code_graph_store.py::test_code_graph_store_searches_fts_and_registers_embeddings -v`
Expected: FAIL because graph FTS sync and embedding registry writes are not implemented yet.

- [ ] **Step 3: Write minimal implementation**

```python
def register_embedding(...):
    connection.execute(
        """
        INSERT INTO embedding_registry(...)
        VALUES (...)
        ON CONFLICT(task_id, item_type, item_ref_id) DO UPDATE SET ...
        """
    )

def search_symbols_fts(...):
    rows = connection.execute(
        """
        SELECT ... FROM code_symbol_fts
        JOIN code_symbol ON ...
        WHERE code_symbol_fts MATCH ? AND code_symbol.task_id = ?
        """
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_code_graph_store.py::test_code_graph_store_searches_fts_and_registers_embeddings -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/code_graph/storage.py tests/unit/test_code_graph_store.py
git commit -m "feat: add code graph fts and embedding registry"
```

### Task 4: Keep existing knowledge indexing behavior green

**Files:**
- Modify: `tests/unit/test_knowledge_store.py`
- Modify: `app/storage/knowledge_store.py`

- [ ] **Step 1: Add regression assertions for existing chunk search**

```python
results = store.search_chunks("health FastAPI", task_id="task-knowledge-1", limit=5)
assert len(results) == 1
assert results[0].path == "app/main.py"
assert "FastAPI" in results[0].content
```

- [ ] **Step 2: Run the targeted storage suite**

Run: `pytest tests/unit/test_knowledge_store.py tests/unit/test_code_graph_store.py -v`
Expected: PASS with both old chunk storage and new graph storage green.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_knowledge_store.py tests/unit/test_code_graph_store.py app/storage/knowledge_store.py app/services/code_graph/storage.py
git commit -m "test: cover legacy and graph storage behavior"
```

### Task 5: Document the S1 storage foundation for the next implementation slice

**Files:**
- Modify: `docs/superpowers/plans/2026-04-11-hybrid-rag-s1-foundation.md`

- [ ] **Step 1: Confirm plan coverage and update notes after implementation**

```markdown
- Graph schema shipped in `app/storage/knowledge_store.py`
- CRUD abstraction shipped in `app/services/code_graph/storage.py`
- Storage tests live in `tests/unit/test_knowledge_store.py` and `tests/unit/test_code_graph_store.py`
```

- [ ] **Step 2: Re-run the final targeted verification**

Run: `pytest tests/unit/test_knowledge_store.py tests/unit/test_code_graph_store.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-04-11-hybrid-rag-s1-foundation.md
git commit -m "docs: capture hybrid rag s1 storage plan"
```
