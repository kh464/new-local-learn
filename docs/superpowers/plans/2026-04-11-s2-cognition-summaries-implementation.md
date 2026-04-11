# S2 Cognition Summaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the current rule-based `summary_zh` generation into a structured repository cognition summary layer that supports LLM-generated Chinese file and symbol descriptions, fallback generation, persistence, and automatic execution during repository analysis.

**Architecture:** Keep the current `CodeGraphBuildPipeline` as the source of graph facts and preserve the existing deterministic `CodeSummaryBuilder` as the fallback. Add structured cognition fields to `code_file` and `code_symbol`, introduce an LLM summary generation service with strict JSON prompts, and run summary generation after graph extraction but before embedding indexing so retrieval can use richer Chinese descriptions.

**Tech Stack:** Python, SQLite/FTS5, FastAPI worker jobs, pytest, HTTP LLM client

---

## File Structure

**Existing files to modify**
- `app/storage/knowledge_store.py`
  Responsibility: extend SQLite schema for structured cognition summary fields.
- `app/services/code_graph/models.py`
  Responsibility: extend file/symbol node dataclasses with cognition summary properties.
- `app/services/code_graph/storage.py`
  Responsibility: persist and read the new cognition summary fields.
- `app/services/code_graph/summary_builder.py`
  Responsibility: keep deterministic fallback summary generation for files and symbols.
- `app/tasks/worker.py`
  Responsibility: register the new summary generation service in the worker context.
- `app/tasks/jobs.py`
  Responsibility: invoke summary generation at the correct point in the analysis pipeline.

**New files to create**
- `app/services/code_graph/summary_prompts.py`
  Responsibility: hold the strict Chinese JSON prompt contracts for file and symbol summaries.
- `app/services/code_graph/llm_summary_service.py`
  Responsibility: call the configured chat-completions client and return validated file/symbol summary payloads.
- `app/services/code_graph/summary_generation_service.py`
  Responsibility: walk graph records for a task, collect evidence, call LLM generation when available, and fall back deterministically when necessary.
- `tests/unit/test_cognition_summary_store.py`
  Responsibility: verify storage and round-trip behavior for structured cognition fields.
- `tests/unit/test_llm_summary_service.py`
  Responsibility: verify prompt usage, JSON validation, and fallback-safe payload generation.
- `tests/unit/test_summary_generation_service.py`
  Responsibility: verify summary generation updates graph records from evidence packs.
- `tests/tasks/test_summary_generation_job.py`
  Responsibility: verify analysis jobs call summary generation in the right order.

---

### Task 1: Extend the graph schema and models for structured cognition summaries

**Files:**
- Modify: `app/storage/knowledge_store.py`
- Modify: `app/services/code_graph/models.py`
- Modify: `app/services/code_graph/storage.py`
- Create: `tests/unit/test_cognition_summary_store.py`

- [ ] **Step 1: Write the failing storage tests**

```python
from app.services.code_graph.models import CodeFileNode, CodeSymbolNode
from app.services.code_graph.storage import CodeGraphStore


def test_code_graph_store_persists_structured_file_summary_fields(tmp_path):
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
                entry_role="backend_entry",
                responsibility_zh="负责创建 FastAPI 应用并注册基础路由",
                upstream_zh="由 Uvicorn 启动时导入",
                downstream_zh="将请求分发到 health 路由",
                keywords_zh=["FastAPI", "入口", "health"],
                summary_source="llm",
                summary_version=1,
                summary_confidence="high",
            )
        ]
    )

    files = store.list_files(task_id="task-1")

    assert files[0].responsibility_zh == "负责创建 FastAPI 应用并注册基础路由"
    assert files[0].upstream_zh == "由 Uvicorn 启动时导入"
    assert files[0].downstream_zh == "将请求分发到 health 路由"
    assert files[0].keywords_zh == ["FastAPI", "入口", "health"]
    assert files[0].summary_source == "llm"
    assert files[0].summary_version == 1
    assert files[0].summary_confidence == "high"


def test_code_graph_store_persists_structured_symbol_summary_fields(tmp_path):
    db_path = tmp_path / "knowledge.db"
    store = CodeGraphStore(db_path)
    store.initialize()

    store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/main.py:app.main.health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=4,
                end_line=5,
                summary_zh="该函数负责健康检查。",
                language="python",
                input_output_zh="无输入，输出健康状态字典",
                side_effects_zh="无外部副作用",
                call_targets_zh="无下游调用",
                callers_zh="由 FastAPI 路由调用",
                summary_source="llm",
                summary_version=1,
                summary_confidence="medium",
            )
        ]
    )

    symbols = store.list_symbols(task_id="task-1")

    assert symbols[0].input_output_zh == "无输入，输出健康状态字典"
    assert symbols[0].side_effects_zh == "无外部副作用"
    assert symbols[0].call_targets_zh == "无下游调用"
    assert symbols[0].callers_zh == "由 FastAPI 路由调用"
    assert symbols[0].summary_source == "llm"
    assert symbols[0].summary_version == 1
    assert symbols[0].summary_confidence == "medium"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_cognition_summary_store.py -v`
Expected: FAIL because the schema, dataclasses, and storage methods do not yet support the new fields.

- [ ] **Step 3: Extend the SQLite schema**

```python
CREATE TABLE IF NOT EXISTS code_file (
    ...,
    responsibility_zh TEXT NOT NULL DEFAULT '',
    upstream_zh TEXT NOT NULL DEFAULT '',
    downstream_zh TEXT NOT NULL DEFAULT '',
    keywords_zh TEXT NOT NULL DEFAULT '[]',
    summary_source TEXT NOT NULL DEFAULT 'rule',
    summary_version INTEGER NOT NULL DEFAULT 0,
    summary_confidence TEXT NOT NULL DEFAULT 'low',
    ...
);

CREATE TABLE IF NOT EXISTS code_symbol (
    ...,
    input_output_zh TEXT NOT NULL DEFAULT '',
    side_effects_zh TEXT NOT NULL DEFAULT '',
    call_targets_zh TEXT NOT NULL DEFAULT '',
    callers_zh TEXT NOT NULL DEFAULT '',
    summary_source TEXT NOT NULL DEFAULT 'rule',
    summary_version INTEGER NOT NULL DEFAULT 0,
    summary_confidence TEXT NOT NULL DEFAULT 'low',
    ...
);
```

- [ ] **Step 4: Extend the node dataclasses**

```python
@dataclass(frozen=True)
class CodeFileNode:
    task_id: str
    path: str
    language: str
    file_kind: str
    summary_zh: str = ""
    entry_role: str | None = None
    responsibility_zh: str = ""
    upstream_zh: str = ""
    downstream_zh: str = ""
    keywords_zh: list[str] = field(default_factory=list)
    summary_source: str = "rule"
    summary_version: int = 0
    summary_confidence: str = "low"
```

```python
@dataclass(frozen=True)
class CodeSymbolNode:
    ...
    input_output_zh: str = ""
    side_effects_zh: str = ""
    call_targets_zh: str = ""
    callers_zh: str = ""
    summary_source: str = "rule"
    summary_version: int = 0
    summary_confidence: str = "low"
```

- [ ] **Step 5: Extend store persistence and row decoding**

```python
connection.execute(
    """
    INSERT INTO code_file(
        task_id, path, language, file_kind, summary_zh, entry_role,
        responsibility_zh, upstream_zh, downstream_zh, keywords_zh,
        summary_source, summary_version, summary_confidence
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(task_id, path) DO UPDATE SET ...
    """
)
```

```python
keywords_zh=json.loads(str(row["keywords_zh"] or "[]"))
```

- [ ] **Step 6: Run storage tests**

Run: `pytest tests/unit/test_cognition_summary_store.py tests/unit/test_code_graph_store.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/storage/knowledge_store.py app/services/code_graph/models.py app/services/code_graph/storage.py tests/unit/test_cognition_summary_store.py
git commit -m "feat: add structured cognition summary fields"
```

---

### Task 2: Add strict prompt contracts and validated LLM summary generation

**Files:**
- Create: `app/services/code_graph/summary_prompts.py`
- Create: `app/services/code_graph/llm_summary_service.py`
- Create: `tests/unit/test_llm_summary_service.py`

- [ ] **Step 1: Write the failing LLM summary tests**

```python
import pytest

from app.services.code_graph.llm_summary_service import LlmSummaryService


@pytest.mark.asyncio
async def test_llm_summary_service_generates_file_summary_payload():
    captured = {}

    class StubClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str):
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return {
                "summary_zh": "该文件负责创建 FastAPI 应用并提供健康检查入口。",
                "responsibility_zh": "负责应用入口初始化与路由挂载",
                "upstream_zh": "由 Uvicorn 启动时导入",
                "downstream_zh": "向 health 处理函数分发请求",
                "keywords_zh": ["FastAPI", "入口", "health"],
                "summary_confidence": "high",
            }

    service = LlmSummaryService(client=StubClient())
    payload = await service.generate_file_summary(
        file_path="app/main.py",
        language="python",
        evidence={
            "symbol_facts": ["定义了 health 函数", "定义了 FastAPI app"],
            "code_snippets": ["app = FastAPI()", "@app.get('/health')"],
        },
    )

    assert payload.summary_zh.startswith("该文件负责创建 FastAPI")
    assert payload.keywords_zh == ["FastAPI", "入口", "health"]
    assert payload.summary_confidence == "high"
    assert "只能输出 JSON" in captured["system_prompt"]
    assert "app/main.py" in captured["user_prompt"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_llm_summary_service.py -v`
Expected: FAIL because the prompt module and summary service do not exist yet.

- [ ] **Step 3: Create file/symbol prompt constants**

```python
FILE_SUMMARY_SYSTEM_PROMPT = """你是代码仓库文件认知摘要生成器。
必须使用简体中文。
只能基于 evidence 生成摘要。
只能输出 JSON。
字段只允许包含：
- summary_zh
- responsibility_zh
- upstream_zh
- downstream_zh
- keywords_zh
- summary_confidence
"""
```

```python
SYMBOL_SUMMARY_SYSTEM_PROMPT = """你是代码仓库符号认知摘要生成器。..."""
```

- [ ] **Step 4: Implement validated payload models and LLM service**

```python
class FileSummaryPayload(BaseModel):
    summary_zh: str
    responsibility_zh: str = ""
    upstream_zh: str = ""
    downstream_zh: str = ""
    keywords_zh: list[str] = Field(default_factory=list)
    summary_confidence: str = "medium"


class LlmSummaryService:
    async def generate_file_summary(self, *, file_path: str, language: str, evidence: dict[str, object]) -> FileSummaryPayload:
        payload = await self._client.complete_json(
            system_prompt=FILE_SUMMARY_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {"file_path": file_path, "language": language, "evidence": evidence},
                ensure_ascii=False,
            ),
        )
        return FileSummaryPayload.model_validate(payload)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_llm_summary_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/code_graph/summary_prompts.py app/services/code_graph/llm_summary_service.py tests/unit/test_llm_summary_service.py
git commit -m "feat: add llm summary generation service"
```

---

### Task 3: Build a summary generation service that consumes graph facts and updates records

**Files:**
- Create: `app/services/code_graph/summary_generation_service.py`
- Modify: `app/services/code_graph/summary_builder.py`
- Create: `tests/unit/test_summary_generation_service.py`

- [ ] **Step 1: Write the failing service tests**

```python
import pytest

from app.services.code_graph.models import CodeFileNode, CodeSymbolNode
from app.services.code_graph.storage import CodeGraphStore
from app.services.code_graph.summary_generation_service import SummaryGenerationService


@pytest.mark.asyncio
async def test_summary_generation_service_updates_file_and_symbol_records(tmp_path):
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
                summary_zh="",
                entry_role="backend_entry",
            )
        ]
    )
    store.upsert_symbols(
        [
            CodeSymbolNode(
                task_id="task-1",
                symbol_id="function:python:app/main.py:app.main.health",
                symbol_kind="function",
                name="health",
                qualified_name="app.main.health",
                file_path="app/main.py",
                start_line=4,
                end_line=5,
                summary_zh="",
                language="python",
            )
        ]
    )

    class StubLlmSummaryService:
        async def generate_file_summary(self, **kwargs):
            from types import SimpleNamespace
            return SimpleNamespace(
                summary_zh="该文件负责 FastAPI 入口。",
                responsibility_zh="负责初始化应用",
                upstream_zh="由 Uvicorn 导入",
                downstream_zh="向路由分发请求",
                keywords_zh=["FastAPI", "入口"],
                summary_confidence="high",
            )

        async def generate_symbol_summary(self, **kwargs):
            from types import SimpleNamespace
            return SimpleNamespace(
                summary_zh="该函数负责健康检查。",
                input_output_zh="无输入，输出健康状态",
                side_effects_zh="无副作用",
                call_targets_zh="无下游调用",
                callers_zh="由 health 路由触发",
                summary_confidence="high",
            )

    service = SummaryGenerationService(
        graph_store=store,
        llm_summary_service=StubLlmSummaryService(),
    )
    await service.build(task_id="task-1", db_path=db_path, repo_root=tmp_path)

    files = store.list_files(task_id="task-1")
    symbols = store.list_symbols(task_id="task-1")

    assert files[0].summary_source == "llm"
    assert files[0].responsibility_zh == "负责初始化应用"
    assert symbols[0].input_output_zh == "无输入，输出健康状态"
    assert symbols[0].summary_source == "llm"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_summary_generation_service.py -v`
Expected: FAIL because the summary generation service does not yet exist.

- [ ] **Step 3: Add richer deterministic fallback builders**

```python
class CodeSummaryBuilder:
    def build_file_payload(self, *, file_node: CodeFileNode, symbols: list[CodeSymbolNode]) -> dict[str, object]:
        return {
            "summary_zh": ...,
            "responsibility_zh": ...,
            "upstream_zh": "",
            "downstream_zh": "",
            "keywords_zh": [...],
            "summary_confidence": "low",
        }

    def build_symbol_payload(self, *, symbol: CodeSymbolNode, outgoing_edges: list[CodeEdge]) -> dict[str, object]:
        return {
            "summary_zh": ...,
            "input_output_zh": ...,
            "side_effects_zh": ...,
            "call_targets_zh": ...,
            "callers_zh": ...,
            "summary_confidence": "low",
        }
```

- [ ] **Step 4: Implement summary generation orchestration**

```python
class SummaryGenerationService:
    async def build(self, *, task_id: str, db_path, repo_root) -> None:
        files = self._graph_store.list_files(task_id=task_id)
        symbols = self._graph_store.list_symbols(task_id=task_id)
        ...
        # for each file/symbol:
        # 1. build evidence pack
        # 2. call llm summary service if available
        # 3. otherwise use deterministic payload
        # 4. update graph store
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_summary_generation_service.py tests/unit/test_code_graph_summary_builder.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/code_graph/summary_generation_service.py app/services/code_graph/summary_builder.py tests/unit/test_summary_generation_service.py
git commit -m "feat: add graph summary generation pipeline"
```

---

### Task 4: Register and invoke summary generation during analysis jobs

**Files:**
- Modify: `app/tasks/worker.py`
- Modify: `app/tasks/jobs.py`
- Create: `tests/tasks/test_summary_generation_job.py`

- [ ] **Step 1: Write the failing job integration test**

```python
import pytest

from app.core.models import TaskState
from app.tasks.jobs import run_analysis_job


@pytest.mark.asyncio
async def test_run_analysis_job_builds_summaries_after_code_graph(fake_job_context):
    captured = {}

    class FakeSummaryGenerationBuilder:
        async def build(self, *, task_id: str, db_path, repo_root):
            captured["task_id"] = task_id
            captured["db_path"] = str(db_path)
            captured["repo_root"] = str(repo_root)

    fake_job_context["summary_generation_builder"] = FakeSummaryGenerationBuilder()

    result = await run_analysis_job(
        fake_job_context,
        "task-summary-ready",
        "https://github.com/octocat/Hello-World",
    )

    assert result["state"] == TaskState.SUCCEEDED.value
    assert captured["task_id"] == "task-summary-ready"
    assert captured["db_path"].endswith("knowledge.db")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/tasks/test_summary_generation_job.py::test_run_analysis_job_builds_summaries_after_code_graph -v`
Expected: FAIL because the worker does not register or call the new summary generation service.

- [ ] **Step 3: Register the service in worker startup**

```python
summary_generation_builder = _build_summary_generation_builder()
if summary_generation_builder is not None:
    ctx["summary_generation_builder"] = summary_generation_builder
```

- [ ] **Step 4: Invoke summary generation in job order**

```python
if code_graph_builder is not None:
    await asyncio.to_thread(...)

summary_generation_builder = _get_ctx_value(ctx, "summary_generation_builder")
if summary_generation_builder is not None:
    summary_build_result = summary_generation_builder.build(
        task_id=task_id,
        db_path=artifacts.knowledge_db_path,
        repo_root=repo_path,
    )
    if inspect.isawaitable(summary_build_result):
        await summary_build_result

if embedding_index_builder is not None:
    ...
```

- [ ] **Step 5: Run task/job tests**

Run: `pytest tests/tasks/test_summary_generation_job.py tests/tasks/test_jobs.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/tasks/worker.py app/tasks/jobs.py tests/tasks/test_summary_generation_job.py
git commit -m "feat: run cognition summaries during analysis jobs"
```

---

### Task 5: Expose the richer summary fields to retrieval and future QA flows

**Files:**
- Modify: `app/services/code_graph/storage.py`
- Modify: `app/services/code_graph/embedding_indexer.py`
- Create: `tests/unit/test_summary_embedding_inputs.py`

- [ ] **Step 1: Write the failing embedding/input test**

```python
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

    captured = {}

    class FakeEmbeddingClient:
        async def embed_texts(self, texts, *, model):
            captured["texts"] = texts
            return [[0.1, 0.2, 0.3] for _ in texts]

    class FakeVectorStore:
        async def ensure_collection(self, *, name, dimension):
            return None

        async def upsert_points(self, *, collection, points):
            return None

    indexer = EmbeddingIndexer(
        graph_store=store,
        embedding_client=FakeEmbeddingClient(),
        vector_store=FakeVectorStore(),
        collection_name="repo_semantic_items",
        embedding_model="demo-embed",
    )
    await indexer.build(task_id="task-1", db_path=db_path)

    assert "负责 FastAPI 初始化" in captured["texts"][0]
    assert "由 Uvicorn 启动导入" in captured["texts"][0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_summary_embedding_inputs.py::test_embedding_indexer_uses_richer_cognition_summary_text -v`
Expected: FAIL because embedding inputs only use the current `summary_zh`.

- [ ] **Step 3: Update summary-to-document conversion**

```python
def _compose_semantic_text(file_node: CodeFileNode) -> str:
    return "\n".join(
        part
        for part in [
            file_node.summary_zh,
            file_node.responsibility_zh,
            file_node.upstream_zh,
            file_node.downstream_zh,
            "关键词：" + "、".join(file_node.keywords_zh) if file_node.keywords_zh else "",
        ]
        if part
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_summary_embedding_inputs.py tests/unit/test_embedding_indexer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/code_graph/embedding_indexer.py tests/unit/test_summary_embedding_inputs.py
git commit -m "feat: feed cognition summaries into embedding index"
```

---

## Acceptance Criteria

- `code_file` and `code_symbol` persist structured Chinese cognition fields, not only `summary_zh`.
- There is an LLM summary service with strict Chinese-only JSON prompts and validated payloads.
- There is a `SummaryGenerationService` that updates graph records from graph evidence.
- The repository analysis job automatically runs summary generation after graph extraction.
- Embedding/indexing paths already consume the richer Chinese cognition summaries.
- Deterministic fallback remains available when no LLM client is configured or the provider fails.

---

## Self-Review

- Spec coverage:
  - `高质量中文文件说明` is covered by Tasks 1-5.
  - `中文描述后续可以升级为 LLM 深度理解生成` is covered by Tasks 2-4.
  - `不破坏现有图谱/知识库/embedding链路` is covered by Tasks 3-5 verification commands.

- Placeholder scan:
  - Every task includes concrete files, concrete tests, exact commands, and expected outcomes.
  - No `TODO`, `TBD`, or hand-wavy “add error handling” placeholders remain.

- Type consistency:
  - The plan consistently uses `summary_generation_builder`, `LlmSummaryService`, and structured file/symbol cognition fields.

---

Plan complete and saved to `docs/superpowers/plans/2026-04-11-s2-cognition-summaries-implementation.md`. Next recommended move is to execute this plan from **Task 1** onward, because it is the smallest independently valuable phase and directly improves your current system’s understanding quality.
