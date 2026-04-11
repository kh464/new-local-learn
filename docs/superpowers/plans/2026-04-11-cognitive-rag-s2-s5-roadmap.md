# Cognitive RAG S2-S5 Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the current hybrid-RAG repository QA system from baseline graph retrieval into a repository cognition system with LLM-generated Chinese summaries, stronger multi-language call graph extraction, cognition-first retrieval, and a frontend "code neural network" exploration view.

**Architecture:** Keep the current SQLite graph store, vector store, and chat orchestration as the base. Add a cognition layer on top of the graph: structured summary generation jobs, summary-aware retrieval, graph traversal, code evidence collection, and finally a dedicated graph visualization API/UI. Deliver the work in phases so each phase is independently testable and deployable.

**Tech Stack:** Python, FastAPI, SQLite/FTS5, Qdrant, pytest, Vue 3, TypeScript, Vitest

---

## Phase Scope Split

This roadmap intentionally splits the work into four delivery phases:

- `S2`: Repository cognition summaries
- `S3`: Multi-language graph extraction
- `S4`: Cognition-first QA orchestration
- `S5`: Code neural network visualization

Each phase should become its own execution plan before implementation starts. This document is the parent roadmap that locks scope, files, interfaces, and verification targets.

---

### Task 1: Define the cognition summary data model

**Files:**
- Modify: `app/storage/knowledge_store.py`
- Modify: `app/services/code_graph/models.py`
- Modify: `app/services/code_graph/storage.py`
- Create: `tests/unit/test_cognition_summary_store.py`

- [ ] **Step 1: Write the failing storage test**

```python
def test_code_graph_store_persists_cognition_summary_fields(tmp_path):
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
                summary_zh="基础摘要",
                entry_role="backend_entry",
                responsibility_zh="负责创建 FastAPI 应用并注册基础路由",
                upstream_zh="由 Uvicorn 启动时加载",
                downstream_zh="向路由处理函数分发请求",
                keywords_zh=["FastAPI", "入口", "路由"],
                summary_source="llm",
                summary_version=1,
                summary_confidence="high",
            )
        ]
    )

    files = graph_store.list_files(task_id="task-1")

    assert files[0].responsibility_zh == "负责创建 FastAPI 应用并注册基础路由"
    assert files[0].upstream_zh == "由 Uvicorn 启动时加载"
    assert files[0].downstream_zh == "向路由处理函数分发请求"
    assert files[0].keywords_zh == ["FastAPI", "入口", "路由"]
    assert files[0].summary_source == "llm"
    assert files[0].summary_version == 1
    assert files[0].summary_confidence == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cognition_summary_store.py::test_code_graph_store_persists_cognition_summary_fields -v`
Expected: FAIL because the schema and models do not yet include cognition summary fields.

- [ ] **Step 3: Extend the schema**

```sql
ALTER TABLE code_file ADD COLUMN responsibility_zh TEXT NOT NULL DEFAULT '';
ALTER TABLE code_file ADD COLUMN upstream_zh TEXT NOT NULL DEFAULT '';
ALTER TABLE code_file ADD COLUMN downstream_zh TEXT NOT NULL DEFAULT '';
ALTER TABLE code_file ADD COLUMN keywords_zh TEXT NOT NULL DEFAULT '[]';
ALTER TABLE code_file ADD COLUMN summary_source TEXT NOT NULL DEFAULT 'rule';
ALTER TABLE code_file ADD COLUMN summary_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE code_file ADD COLUMN summary_confidence TEXT NOT NULL DEFAULT 'low';

ALTER TABLE code_symbol ADD COLUMN input_output_zh TEXT NOT NULL DEFAULT '';
ALTER TABLE code_symbol ADD COLUMN side_effects_zh TEXT NOT NULL DEFAULT '';
ALTER TABLE code_symbol ADD COLUMN call_targets_zh TEXT NOT NULL DEFAULT '';
ALTER TABLE code_symbol ADD COLUMN callers_zh TEXT NOT NULL DEFAULT '';
ALTER TABLE code_symbol ADD COLUMN summary_source TEXT NOT NULL DEFAULT 'rule';
ALTER TABLE code_symbol ADD COLUMN summary_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE code_symbol ADD COLUMN summary_confidence TEXT NOT NULL DEFAULT 'low';
```

- [ ] **Step 4: Extend the Python models and storage serialization**

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

- [ ] **Step 5: Run the storage tests**

Run: `pytest tests/unit/test_cognition_summary_store.py tests/unit/test_code_graph_store.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/storage/knowledge_store.py app/services/code_graph/models.py app/services/code_graph/storage.py tests/unit/test_cognition_summary_store.py
git commit -m "feat: add cognition summary data model"
```

---

### Task 2: Add an LLM summary generation service for files and symbols

**Files:**
- Create: `app/services/code_graph/summary_prompts.py`
- Create: `app/services/code_graph/llm_summary_service.py`
- Modify: `app/services/code_graph/summary_builder.py`
- Create: `tests/unit/test_llm_summary_service.py`

- [ ] **Step 1: Write the failing service test**

```python
@pytest.mark.asyncio
async def test_llm_summary_service_generates_structured_file_summary():
    class StubClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str):
            return {
                "summary_zh": "该文件负责创建 FastAPI 应用并暴露基础健康检查路由。",
                "responsibility_zh": "负责应用入口初始化与路由挂载",
                "upstream_zh": "由 Uvicorn 启动时导入",
                "downstream_zh": "向 health 路由处理函数分发请求",
                "keywords_zh": ["FastAPI", "入口", "health"],
                "summary_confidence": "high",
            }

    service = LlmSummaryService(client=StubClient())
    result = await service.generate_file_summary(
        file_path="app/main.py",
        language="python",
        symbol_facts=["定义了函数 health", "定义了 FastAPI app"],
        code_snippets=["app = FastAPI()", "@app.get('/health')"],
    )

    assert result.summary_zh.startswith("该文件负责创建 FastAPI")
    assert result.keywords_zh == ["FastAPI", "入口", "health"]
    assert result.summary_confidence == "high"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_llm_summary_service.py::test_llm_summary_service_generates_structured_file_summary -v`
Expected: FAIL because the LLM summary service does not exist yet.

- [ ] **Step 3: Create prompt contracts**

```python
FILE_SUMMARY_SYSTEM_PROMPT = """你是代码仓库文件摘要生成器...
只能输出 JSON:
- summary_zh
- responsibility_zh
- upstream_zh
- downstream_zh
- keywords_zh
- summary_confidence
"""
```

- [ ] **Step 4: Implement the summary service**

```python
class LlmSummaryService:
    async def generate_file_summary(self, *, file_path: str, language: str, symbol_facts: list[str], code_snippets: list[str]) -> FileSummaryPayload:
        payload = await self._client.complete_json(
            system_prompt=FILE_SUMMARY_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "file_path": file_path,
                    "language": language,
                    "symbol_facts": symbol_facts,
                    "code_snippets": code_snippets,
                },
                ensure_ascii=False,
            ),
        )
        return FileSummaryPayload.model_validate(payload)
```

- [ ] **Step 5: Keep the existing `CodeSummaryBuilder` as deterministic fallback**

```python
class CodeSummaryBuilder:
    def build_file_summary(...): ...
    def build_symbol_summary(...): ...
```

- [ ] **Step 6: Run the summary tests**

Run: `pytest tests/unit/test_llm_summary_service.py tests/unit/test_code_graph_summary_builder.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add app/services/code_graph/summary_prompts.py app/services/code_graph/llm_summary_service.py app/services/code_graph/summary_builder.py tests/unit/test_llm_summary_service.py
git commit -m "feat: add llm cognition summary generation"
```

---

### Task 3: Integrate summary generation into the repository analysis job

**Files:**
- Modify: `app/services/code_graph/pipeline.py`
- Modify: `app/tasks/worker.py`
- Modify: `app/tasks/jobs.py`
- Create: `tests/tasks/test_summary_generation_job.py`

- [ ] **Step 1: Write the failing job test**

```python
@pytest.mark.asyncio
async def test_run_analysis_job_builds_llm_summaries_after_graph_build(fake_job_context):
    captured = {}

    class FakeSummaryBuilder:
        async def build(self, *, task_id: str, db_path, repo_root):
            captured["task_id"] = task_id
            captured["db_path"] = str(db_path)
            captured["repo_root"] = str(repo_root)

    fake_job_context["summary_generation_builder"] = FakeSummaryBuilder()

    await run_analysis_job(fake_job_context, "task-summary", "https://github.com/octocat/Hello-World")

    assert captured["task_id"] == "task-summary"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/tasks/test_summary_generation_job.py::test_run_analysis_job_builds_llm_summaries_after_graph_build -v`
Expected: FAIL because the worker context does not register or invoke summary generation.

- [ ] **Step 3: Register the summary generation service in worker startup**

```python
summary_generation_builder = _build_summary_generation_builder()
if summary_generation_builder is not None:
    ctx["summary_generation_builder"] = summary_generation_builder
```

- [ ] **Step 4: Invoke summary generation after graph build and before embedding build**

```python
summary_generation_builder = _get_ctx_value(ctx, "summary_generation_builder")
if summary_generation_builder is not None:
    await _maybe_await(
        summary_generation_builder.build(
            task_id=task_id,
            db_path=artifacts.knowledge_db_path,
            repo_root=artifacts.repo_dir,
        )
    )
```

- [ ] **Step 5: Run the task/job tests**

Run: `pytest tests/tasks/test_summary_generation_job.py tests/tasks/test_jobs.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/code_graph/pipeline.py app/tasks/worker.py app/tasks/jobs.py tests/tasks/test_summary_generation_job.py
git commit -m "feat: integrate cognition summary generation into analysis job"
```

---

### Task 4: Add TypeScript graph extraction

**Files:**
- Create: `app/services/code_graph/adapters/typescript.py`
- Modify: `app/services/code_graph/adapters/base.py`
- Modify: `app/services/code_graph/pipeline.py`
- Create: `tests/unit/test_typescript_code_graph_adapter.py`

- [ ] **Step 1: Write the failing adapter test**

```python
def test_typescript_adapter_extracts_component_and_fetch_call(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    file_path = repo_root / "web" / "App.tsx"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(
        "export function App() { async function load() { return fetch('/health') } return null }",
        encoding="utf-8",
    )

    adapter = TypeScriptCodeGraphAdapter()
    result = adapter.extract_file(task_id="task-1", repo_root=repo_root, file_path=file_path)

    assert any(symbol.qualified_name.endswith("App") for symbol in result.symbols)
    assert any(call.callee_name == "fetch" for call in result.unresolved_calls)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_typescript_code_graph_adapter.py::test_typescript_adapter_extracts_component_and_fetch_call -v`
Expected: FAIL because the adapter does not exist yet.

- [ ] **Step 3: Implement the adapter**

```python
class TypeScriptCodeGraphAdapter(CodeGraphAdapter):
    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in {".ts", ".tsx", ".js", ".jsx"}

    def extract_file(self, *, task_id: str, repo_root: Path, file_path: Path) -> ExtractionResult:
        source = file_path.read_text(encoding="utf-8")
        # initial implementation: regex/lightweight parser for exported functions, classes, fetch calls
```

- [ ] **Step 4: Register the adapter in the pipeline**

```python
self._adapters = adapters or [PythonCodeGraphAdapter(), TypeScriptCodeGraphAdapter()]
```

- [ ] **Step 5: Run adapter and pipeline tests**

Run: `pytest tests/unit/test_typescript_code_graph_adapter.py tests/unit/test_code_graph_pipeline.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/code_graph/adapters/typescript.py app/services/code_graph/pipeline.py tests/unit/test_typescript_code_graph_adapter.py
git commit -m "feat: add typescript code graph adapter"
```

---

### Task 5: Add Java graph extraction

**Files:**
- Create: `app/services/code_graph/adapters/java.py`
- Modify: `app/services/code_graph/pipeline.py`
- Create: `tests/unit/test_java_code_graph_adapter.py`

- [ ] **Step 1: Write the failing adapter test**

```python
def test_java_adapter_extracts_class_and_method(tmp_path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    file_path = repo_root / "src" / "main" / "java" / "demo" / "App.java"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(
        "package demo; public class App { public String hello() { return service.run(); } }",
        encoding="utf-8",
    )

    adapter = JavaCodeGraphAdapter()
    result = adapter.extract_file(task_id="task-1", repo_root=repo_root, file_path=file_path)

    assert any(symbol.symbol_kind == "class" and symbol.name == "App" for symbol in result.symbols)
    assert any(symbol.name == "hello" for symbol in result.symbols)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_java_code_graph_adapter.py::test_java_adapter_extracts_class_and_method -v`
Expected: FAIL because the Java adapter does not exist yet.

- [ ] **Step 3: Implement the Java adapter**

```python
class JavaCodeGraphAdapter(CodeGraphAdapter):
    def supports(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == ".java"
```

- [ ] **Step 4: Register the adapter**

```python
self._adapters = adapters or [
    PythonCodeGraphAdapter(),
    TypeScriptCodeGraphAdapter(),
    JavaCodeGraphAdapter(),
]
```

- [ ] **Step 5: Run adapter and pipeline tests**

Run: `pytest tests/unit/test_java_code_graph_adapter.py tests/unit/test_code_graph_pipeline.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/code_graph/adapters/java.py app/services/code_graph/pipeline.py tests/unit/test_java_code_graph_adapter.py
git commit -m "feat: add java code graph adapter"
```

---

### Task 6: Extend graph semantics beyond basic symbol containment

**Files:**
- Modify: `app/services/code_graph/models.py`
- Modify: `app/services/code_graph/adapters/python.py`
- Modify: `app/services/code_graph/adapters/typescript.py`
- Modify: `app/services/code_graph/adapters/java.py`
- Create: `tests/unit/test_graph_edge_semantics.py`

- [ ] **Step 1: Write the failing graph semantics test**

```python
def test_graph_edges_capture_imports_calls_and_route_binding(tmp_path):
    ...
    assert any(edge.edge_kind == "imports" for edge in result.edges)
    assert any(edge.edge_kind == "calls" for edge in result.edges)
    assert any(edge.edge_kind == "route_bind" for edge in result.edges)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_edge_semantics.py::test_graph_edges_capture_imports_calls_and_route_binding -v`
Expected: FAIL because the current adapters do not emit the richer edge taxonomy.

- [ ] **Step 3: Extend edge kinds and adapters**

```python
ALLOWED_EDGE_KINDS = {
    "contains",
    "imports",
    "calls",
    "inherits",
    "implements",
    "route_bind",
    "db_access",
    "event_flow",
}
```

- [ ] **Step 4: Run graph extraction tests**

Run: `pytest tests/unit/test_graph_edge_semantics.py tests/unit/test_python_code_graph_adapter.py tests/unit/test_typescript_code_graph_adapter.py tests/unit/test_java_code_graph_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/code_graph/models.py app/services/code_graph/adapters/python.py app/services/code_graph/adapters/typescript.py app/services/code_graph/adapters/java.py tests/unit/test_graph_edge_semantics.py
git commit -m "feat: enrich code graph edge semantics"
```

---

### Task 7: Add cognition-aware retrieval over summaries and graph nodes

**Files:**
- Create: `app/services/cognition/models.py`
- Create: `app/services/cognition/retriever.py`
- Create: `app/services/cognition/ranker.py`
- Modify: `app/services/chat/question_analyzer.py`
- Create: `tests/unit/test_cognition_retriever.py`

- [ ] **Step 1: Write the failing retrieval test**

```python
def test_cognition_retriever_prefers_summary_hits_before_raw_code_hits(tmp_path):
    ...
    results = retriever.retrieve(
        task_id="task-1",
        question="项目里是否有知识库能力",
        limit=5,
    )

    assert results[0].path == "app/services/knowledge/retriever.py"
    assert results[0].reason == "summary_match"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cognition_retriever.py::test_cognition_retriever_prefers_summary_hits_before_raw_code_hits -v`
Expected: FAIL because cognition-aware retrieval does not exist yet.

- [ ] **Step 3: Implement retrieval over summary fields**

```python
class CognitiveRetriever:
    def retrieve(self, *, task_id: str, question: str, limit: int = 10) -> list[CognitiveHit]:
        # search file summaries, symbol summaries, keywords_zh, and semantic embeddings first
```

- [ ] **Step 4: Add ranking signals**

```python
score = summary_score + keyword_score + graph_centrality_score + semantic_score
```

- [ ] **Step 5: Run cognition retrieval tests**

Run: `pytest tests/unit/test_cognition_retriever.py tests/unit/test_question_analyzer.py tests/unit/test_code_graph_retrievers.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/cognition/models.py app/services/cognition/retriever.py app/services/cognition/ranker.py app/services/chat/question_analyzer.py tests/unit/test_cognition_retriever.py
git commit -m "feat: add cognition-aware retrieval"
```

---

### Task 8: Add graph traversal and evidence collection for question answering

**Files:**
- Create: `app/services/cognition/graph_traverser.py`
- Create: `app/services/cognition/evidence_collector.py`
- Modify: `app/services/code_graph/graph_expander.py`
- Modify: `app/services/code_graph/code_locator.py`
- Create: `tests/unit/test_graph_traverser.py`

- [ ] **Step 1: Write the failing traversal test**

```python
def test_graph_traverser_expands_from_cognitive_seed_to_related_call_chain(tmp_path):
    ...
    traversal = traverser.expand(task_id="task-1", seed_ids=["symbol:app.main.health"])
    assert traversal.nodes
    assert traversal.edges
    assert any(edge["kind"] == "calls" for edge in traversal.edges)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_traverser.py::test_graph_traverser_expands_from_cognitive_seed_to_related_call_chain -v`
Expected: FAIL because the cognition graph traverser does not exist yet.

- [ ] **Step 3: Implement graph expansion**

```python
class CognitiveGraphTraverser:
    def expand(self, *, task_id: str, seed_ids: list[str], max_hops: int = 3, max_nodes: int = 40) -> TraversalResult:
        ...
```

- [ ] **Step 4: Implement code evidence collection**

```python
class EvidenceCollector:
    def collect(self, *, traversal: TraversalResult) -> EvidenceCollection:
        # resolve file snippets, symbol definitions, and route nodes
```

- [ ] **Step 5: Run traversal and evidence tests**

Run: `pytest tests/unit/test_graph_traverser.py tests/unit/test_code_graph_evidence.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/cognition/graph_traverser.py app/services/cognition/evidence_collector.py app/services/code_graph/graph_expander.py app/services/code_graph/code_locator.py tests/unit/test_graph_traverser.py
git commit -m "feat: add cognition graph traversal and evidence collection"
```

---

### Task 9: Replace the current QA orchestration with cognition-first routing

**Files:**
- Modify: `app/services/chat/orchestrator.py`
- Modify: `app/api/routes/tasks.py`
- Modify: `app/services/chat/answer_composer.py`
- Create: `tests/unit/test_cognition_orchestrator.py`

- [ ] **Step 1: Write the failing orchestrator test**

```python
@pytest.mark.asyncio
async def test_orchestrator_uses_cognition_locator_before_code_locator():
    ...
    response = await orchestrator.answer_question(
        task_id="task-1",
        db_path="knowledge.db",
        repo_map_path=None,
        question="项目中是否存在知识库",
        history=[],
    )

    assert response.planner_metadata.planning_source == "cognitive_rag"
    assert response.answer_debug is not None
    assert response.answer_debug.confirmed_facts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cognition_orchestrator.py::test_orchestrator_uses_cognition_locator_before_code_locator -v`
Expected: FAIL because the orchestrator still uses the current hybrid path directly.

- [ ] **Step 3: Inject cognition components**

```python
TaskChatOrchestrator(
    cognitive_retriever=...,
    cognitive_ranker=...,
    cognitive_graph_traverser=...,
    evidence_collector=...,
)
```

- [ ] **Step 4: Add a new planning source label**

```python
PlannerMetadata(
    planning_source="cognitive_rag",
    ...
)
```

- [ ] **Step 5: Run orchestrator and API tests**

Run: `pytest tests/unit/test_cognition_orchestrator.py tests/unit/test_chat_orchestrator.py tests/api/test_task_chat_api.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/chat/orchestrator.py app/api/routes/tasks.py app/services/chat/answer_composer.py tests/unit/test_cognition_orchestrator.py
git commit -m "feat: add cognition-first qa orchestration"
```

---

### Task 10: Add graph query APIs for frontend exploration

**Files:**
- Create: `app/api/routes/graph.py`
- Modify: `app/main.py`
- Create: `tests/api/test_graph_api.py`

- [ ] **Step 1: Write the failing API test**

```python
@pytest.mark.asyncio
async def test_graph_api_returns_repository_subgraph(api_client):
    response = await api_client.get("/api/v1/tasks/task-1/graph?view=repository")
    assert response.status_code == 200
    payload = response.json()
    assert "nodes" in payload
    assert "edges" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_graph_api.py::test_graph_api_returns_repository_subgraph -v`
Expected: FAIL because the graph API does not exist yet.

- [ ] **Step 3: Implement repository/module/symbol graph endpoints**

```python
@router.get("/tasks/{task_id}/graph")
async def get_task_graph(task_id: str, view: str = "repository", symbol_id: str | None = None):
    ...
```

- [ ] **Step 4: Run API tests**

Run: `pytest tests/api/test_graph_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/graph.py app/main.py tests/api/test_graph_api.py
git commit -m "feat: add graph exploration api"
```

---

### Task 11: Build the frontend code neural network panel

**Files:**
- Create: `web/src/components/CodeGraphPanel.vue`
- Create: `web/src/components/CodeGraphPanel.spec.ts`
- Create: `web/src/services/graphApi.ts`
- Modify: `web/src/services/api.ts`
- Modify: `web/src/types/contracts.ts`
- Modify: `web/src/pages/TaskDetailPage.vue`

- [ ] **Step 1: Write the failing frontend test**

```ts
it('renders graph nodes and highlights the selected node details', async () => {
  ...
  expect(wrapper.text()).toContain('app/main.py')
  expect(wrapper.text()).toContain('已确认入口文件')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/components/CodeGraphPanel.spec.ts`
Expected: FAIL because the graph panel does not exist yet.

- [ ] **Step 3: Implement the graph API client**

```ts
export async function fetchTaskGraph(taskId: string, view: string): Promise<TaskGraphPayload> {
  ...
}
```

- [ ] **Step 4: Implement the panel**

```vue
<template>
  <section class="code-graph-panel">
    <aside class="code-graph-panel__canvas"></aside>
    <aside class="code-graph-panel__details"></aside>
  </section>
</template>
```

- [ ] **Step 5: Mount the panel inside task detail**

```vue
<CodeGraphPanel v-if="status?.knowledge_state === 'ready'" :task-id="taskId" />
```

- [ ] **Step 6: Run frontend tests and build**

Run: `npm test -- src/components/CodeGraphPanel.spec.ts src/pages/TaskDetailPage.spec.ts`
Expected: PASS

Run: `npm run build`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add web/src/components/CodeGraphPanel.vue web/src/components/CodeGraphPanel.spec.ts web/src/services/graphApi.ts web/src/services/api.ts web/src/types/contracts.ts web/src/pages/TaskDetailPage.vue
git commit -m "feat: add code neural network graph panel"
```

---

### Task 12: Add question-to-graph highlighting and answer-to-graph linkage

**Files:**
- Modify: `app/core/models.py`
- Modify: `app/services/chat/orchestrator.py`
- Modify: `web/src/components/TaskChatPanel.vue`
- Modify: `web/src/components/CodeGraphPanel.vue`
- Create: `tests/unit/test_answer_graph_linkage.py`
- Create: `web/src/components/CodeGraphPanelLinkage.spec.ts`

- [ ] **Step 1: Write the failing linkage tests**

```python
def test_answer_contains_related_graph_node_ids():
    ...
    assert response.answer_debug.related_node_ids == ["symbol:python:app/main.py:health"]
```

```ts
it('highlights graph nodes referenced by the selected answer', async () => {
  ...
  expect(wrapper.find('[data-node-id="symbol:python:app/main.py:health"]').classes()).toContain('is-active')
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_answer_graph_linkage.py -v`
Expected: FAIL

Run: `npm test -- src/components/CodeGraphPanelLinkage.spec.ts`
Expected: FAIL

- [ ] **Step 3: Extend the answer debug payload**

```python
class AnswerDebug(BaseModel):
    confirmed_facts: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Wire answer-to-graph selection**

```ts
watch(selectedAnswerDebug, () => {
  highlightedNodeIds.value = selectedAnswerDebug.value?.related_node_ids ?? []
})
```

- [ ] **Step 5: Run linkage tests and frontend build**

Run: `pytest tests/unit/test_answer_graph_linkage.py -v`
Expected: PASS

Run: `npm test -- src/components/CodeGraphPanelLinkage.spec.ts src/components/TaskChatPanel.spec.ts`
Expected: PASS

Run: `npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/models.py app/services/chat/orchestrator.py web/src/components/TaskChatPanel.vue web/src/components/CodeGraphPanel.vue tests/unit/test_answer_graph_linkage.py web/src/components/CodeGraphPanelLinkage.spec.ts
git commit -m "feat: link answers to code graph highlights"
```

---

## Phase Acceptance Criteria

- `S2` acceptance:
  - File and symbol summaries are persisted with structured Chinese cognition fields.
  - Summary generation supports deterministic fallback and LLM mode.
  - Summary generation runs automatically after graph extraction.

- `S3` acceptance:
  - Python, TypeScript, and Java repositories all build graph records.
  - Graph edges include more than `contains`; at minimum `imports`, `calls`, and `route_bind` work.

- `S4` acceptance:
  - Questions are answered through cognition retrieval before raw code expansion.
  - `planner_metadata.planning_source` can report `cognitive_rag`.
  - `answer_debug` exposes confirmed facts and evidence gaps.

- `S5` acceptance:
  - Frontend can query and render repository/module/symbol graphs.
  - Answers can highlight related graph nodes.
  - The task detail page exposes a code neural network exploration panel.

---

## Self-Review

- Spec coverage:
  - `全仓库深度理解` is covered by Tasks 1-3 and 7-9.
  - `高质量中文文件说明` is covered by Tasks 1-3.
  - `强调用链网络` is covered by Tasks 4-6 and 8-12.
  - `代码神经网络图` is covered by Tasks 10-12.

- Placeholder scan:
  - No `TODO` or `TBD` placeholders remain.
  - Every task lists files, tests, commands, and the expected failure/pass signal.

- Type consistency:
  - `AnswerDebug`, `CodeFileNode`, `CodeSymbolNode`, cognition retriever classes, and graph API payloads are named consistently across the plan.

---

Plan complete and saved to `docs/superpowers/plans/2026-04-11-cognitive-rag-s2-s5-roadmap.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
