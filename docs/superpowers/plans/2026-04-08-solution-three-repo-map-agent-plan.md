# Solution Three Repo Map Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有方案二代码知识库之上增加任务级仓库认知图，使问答先基于代码结构和调用链理解项目，再回落到真实代码证据。

**Architecture:** 保留 `knowledge.db` 作为代码证据层，新增 `repo_map.json` 作为仓库认知层。任务成功后先完成知识库构建，再构建认知图；问答服务新增问题分类与认知图召回，优先利用入口、符号、关系边和调用链摘要组织上下文，再补齐代码片段并生成中文回答。

**Tech Stack:** FastAPI, Pydantic, SQLite/FTS5, JSON artifact files, Vue 3, Vitest, Pytest

---

## 文件结构

- Modify: `D:/ai-agent/new-local-learn/app/storage/artifacts.py`
- Modify: `D:/ai-agent/new-local-learn/app/core/models.py`
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/repo_map_builder.py`
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/question_planner.py`
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/repo_map_loader.py`
- Modify: `D:/ai-agent/new-local-learn/app/services/llm/knowledge_chat.py`
- Modify: `D:/ai-agent/new-local-learn/app/tasks/jobs.py`
- Modify: `D:/ai-agent/new-local-learn/app/tasks/worker.py`
- Modify: `D:/ai-agent/new-local-learn/app/api/routes/tasks.py`
- Create: `D:/ai-agent/new-local-learn/tests/unit/test_repo_map_builder.py`
- Create: `D:/ai-agent/new-local-learn/tests/unit/test_question_planner.py`
- Modify: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_chat_service.py`
- Modify: `D:/ai-agent/new-local-learn/tests/tasks/test_jobs.py`
- Modify: `D:/ai-agent/new-local-learn/tests/api/test_task_chat_api.py`
- Modify: `D:/ai-agent/new-local-learn/web/src/types/contracts.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/services/api.spec.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.vue`
- Modify: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.spec.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.vue`
- Modify: `D:/ai-agent/new-local-learn/README.md`

## Task 1: 定义认知图产物路径与响应模型

**Files:**
- Modify: `D:/ai-agent/new-local-learn/app/storage/artifacts.py`
- Modify: `D:/ai-agent/new-local-learn/app/core/models.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_bootstrap.py`

- [ ] **Step 1: 写失败测试，断言任务产物包含 `repo_map.json` 路径，聊天响应模型支持认知图命中信息。**

```python
def test_artifact_paths_and_chat_models_include_repo_map(tmp_path):
    paths = ArtifactPaths(base_dir=tmp_path, task_id="task-1")
    response = TaskChatResponse(
        answer="示例",
        graph_evidence=[TaskGraphEvidence(kind="call_chain", label="前端到后端")],
    )
    assert paths.repo_map_path.name == "repo_map.json"
    assert response.graph_evidence[0].kind == "call_chain"
```

- [ ] **Step 2: 运行测试，确认当前因缺失字段而失败。**

Run: `python -m pytest tests/unit/test_bootstrap.py -q`
Expected: FAIL with missing `repo_map_path` or chat graph evidence fields

- [ ] **Step 3: 增加 `ArtifactPaths.repo_map_path`，并在聊天模型中加入 `graph_evidence` 结构。**

```python
class TaskGraphEvidence(BaseModel):
    kind: Literal["entrypoint", "symbol", "edge", "call_chain"]
    label: str
    detail: str | None = None
    path: str | None = None

class TaskChatResponse(BaseModel):
    answer: str
    graph_evidence: list[TaskGraphEvidence] = Field(default_factory=list)
```

- [ ] **Step 4: 重新运行测试，确认通过。**

Run: `python -m pytest tests/unit/test_bootstrap.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/storage/artifacts.py app/core/models.py tests/unit/test_bootstrap.py
git commit -m "feat: add repo map artifact and graph evidence models"
```

## Task 2: 实现仓库认知图构建器

**Files:**
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/repo_map_builder.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_repo_map_builder.py`

- [ ] **Step 1: 写失败测试，覆盖文件节点、符号节点、import 边、前后端调用边和入口识别。**

```python
def test_repo_map_builder_extracts_nodes_edges_and_entrypoints(tmp_path):
    result = RepoMapBuilder().build(task_id="task-1", repo_path=repo_path, output_path=repo_map_path)
    assert result["entrypoints"]["backend"]["file_path"] == "app/main.py"
    assert any(edge["type"] == "imports" for edge in result["edges"])
    assert any(edge["type"] == "maps_to_backend" for edge in result["edges"])
```

- [ ] **Step 2: 运行测试，确认当前缺少构建器而失败。**

Run: `python -m pytest tests/unit/test_repo_map_builder.py -q`
Expected: FAIL with module or class not found

- [ ] **Step 3: 实现 `RepoMapBuilder`，首版静态提取文件节点、符号节点、关系边、入口点和调用链摘要，并写出 JSON。**

```python
class RepoMapBuilder:
    def build(self, *, task_id: str, repo_path: Path, output_path: Path) -> dict[str, object]:
        file_nodes = self._collect_file_nodes(repo_path)
        symbol_nodes = self._collect_symbol_nodes(file_nodes)
        edges = self._collect_edges(file_nodes, symbol_nodes)
        payload = {
            "task_id": task_id,
            "file_nodes": file_nodes,
            "symbol_nodes": symbol_nodes,
            "edges": edges,
            "entrypoints": self._collect_entrypoints(file_nodes, symbol_nodes, edges),
            "call_chains": self._collect_call_chains(edges),
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
```

- [ ] **Step 4: 重新运行测试，确认通过。**

Run: `python -m pytest tests/unit/test_repo_map_builder.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/knowledge/repo_map_builder.py tests/unit/test_repo_map_builder.py
git commit -m "feat: build repo map artifacts from repository structure"
```

## Task 3: 实现问题分类与认知图召回

**Files:**
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/question_planner.py`
- Create: `D:/ai-agent/new-local-learn/app/services/knowledge/repo_map_loader.py`
- Test: `D:/ai-agent/new-local-learn/tests/unit/test_question_planner.py`

- [ ] **Step 1: 写失败测试，覆盖入口定位、调用链、能力存在性问题的分类与节点召回。**

```python
def test_question_planner_prefers_call_chain_and_entrypoints():
    planner = QuestionPlanner(repo_map_payload)
    plan = planner.plan("这个仓库的后端入口在哪里？")
    assert plan.question_type == "entrypoint"
    assert plan.entrypoint_hits[0]["file_path"] == "app/main.py"
```

- [ ] **Step 2: 运行测试，确认当前缺少规划器而失败。**

Run: `python -m pytest tests/unit/test_question_planner.py -q`
Expected: FAIL with missing planner/loader modules

- [ ] **Step 3: 实现问题分类器和认知图加载器，输出结构化计划对象。**

```python
class QuestionPlanner:
    def plan(self, question: str) -> QuestionPlan:
        question_type = self._classify(question)
        return QuestionPlan(
            question_type=question_type,
            entrypoint_hits=self._find_entrypoints(question_type, question),
            symbol_hits=self._find_symbols(question),
            edge_hits=self._find_edges(question_type, question),
            call_chain_hits=self._find_call_chains(question_type, question),
        )
```

- [ ] **Step 4: 重新运行测试，确认通过。**

Run: `python -m pytest tests/unit/test_question_planner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/knowledge/question_planner.py app/services/knowledge/repo_map_loader.py tests/unit/test_question_planner.py
git commit -m "feat: add repo map question planner"
```

## Task 4: 将认知图接入任务流水线

**Files:**
- Modify: `D:/ai-agent/new-local-learn/app/tasks/jobs.py`
- Modify: `D:/ai-agent/new-local-learn/app/tasks/worker.py`
- Modify: `D:/ai-agent/new-local-learn/tests/tasks/test_jobs.py`

- [ ] **Step 1: 写失败测试，断言知识库之后还会生成 `repo_map.json`，并在状态中保留认知图可用性。**

```python
async def test_run_analysis_job_builds_repo_map_after_knowledge(fake_job_context):
    result = await run_analysis_job(fake_job_context, "task-map", github_url)
    assert Path(fake_job_context["artifacts_dir"] / "task-map" / "repo_map.json").is_file()
```

- [ ] **Step 2: 运行测试，确认当前仅构建知识库、不构建认知图。**

Run: `python -m pytest tests/tasks/test_jobs.py -q`
Expected: FAIL with missing `repo_map.json`

- [ ] **Step 3: 在任务流水线中注入 `RepoMapBuilder`，在知识库成功后构建认知图；认知图失败时保留方案二可用。**

```python
repo_map_builder = _get_ctx_value(ctx, "repo_map_builder")
repo_map_error = None
try:
    await asyncio.to_thread(
        repo_map_builder.build,
        task_id=task_id,
        repo_path=repo_path,
        output_path=artifacts.repo_map_path,
    )
except Exception as exc:
    repo_map_error = str(exc)
```

- [ ] **Step 4: 重新运行测试，确认通过。**

Run: `python -m pytest tests/tasks/test_jobs.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/tasks/jobs.py app/tasks/worker.py tests/tasks/test_jobs.py
git commit -m "feat: build repo map artifacts in analysis pipeline"
```

## Task 5: 增强知识问答服务为“认知图优先”

**Files:**
- Modify: `D:/ai-agent/new-local-learn/app/services/llm/knowledge_chat.py`
- Modify: `D:/ai-agent/new-local-learn/tests/unit/test_knowledge_chat_service.py`

- [ ] **Step 1: 写失败测试，断言问答会先使用认知图命中，再补代码证据，并回传 `graph_evidence`。**

```python
@pytest.mark.asyncio
async def test_knowledge_chat_service_returns_graph_evidence(tmp_path):
    response = await service.answer_question(...)
    assert response.graph_evidence[0].kind == "entrypoint"
    assert response.citations[0].path == "app/main.py"
```

- [ ] **Step 2: 运行测试，确认当前响应没有认知图命中信息。**

Run: `python -m pytest tests/unit/test_knowledge_chat_service.py -q`
Expected: FAIL with missing `graph_evidence`

- [ ] **Step 3: 加载 `repo_map.json`，执行问题规划，先构造认知图上下文，再补充代码上下文，并在响应中带回 `graph_evidence`。**

```python
repo_map = RepoMapLoader().load(repo_map_path)
plan = QuestionPlanner(repo_map).plan(question)
graph_evidence = build_graph_evidence(plan)
citations = retrieve_code_citations(plan, question)
```

- [ ] **Step 4: 重新运行测试，确认通过。**

Run: `python -m pytest tests/unit/test_knowledge_chat_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/llm/knowledge_chat.py tests/unit/test_knowledge_chat_service.py
git commit -m "feat: answer questions with repo map context"
```

## Task 6: 升级任务聊天 API 透出认知图证据

**Files:**
- Modify: `D:/ai-agent/new-local-learn/app/api/routes/tasks.py`
- Modify: `D:/ai-agent/new-local-learn/tests/api/test_task_chat_api.py`

- [ ] **Step 1: 写失败测试，断言聊天响应包含 `graph_evidence`，认知图不存在时仍允许降级到方案二。**

```python
assert payload["assistant_message"]["graph_evidence"][0]["kind"] == "entrypoint"
```

- [ ] **Step 2: 运行测试，确认当前 API 未透出认知图信息。**

Run: `python -m pytest tests/api/test_task_chat_api.py -q`
Expected: FAIL with missing `graph_evidence`

- [ ] **Step 3: 在聊天 API 中传入 `repo_map.json` 路径，保留认知图缺失时的降级分支。**

```python
repo_map_path = ArtifactPaths(base_dir=settings.artifacts_dir, task_id=task_id).repo_map_path
answer = await chat_service.answer_question(
    task_id=task_id,
    db_path=db_path,
    repo_map_path=repo_map_path if repo_map_path.is_file() else None,
    question=user_message.content,
    history=history,
)
```

- [ ] **Step 4: 重新运行测试，确认通过。**

Run: `python -m pytest tests/api/test_task_chat_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/api/routes/tasks.py tests/api/test_task_chat_api.py
git commit -m "feat: expose repo map evidence in task chat api"
```

## Task 7: 前端展示认知图结论与代码证据

**Files:**
- Modify: `D:/ai-agent/new-local-learn/web/src/types/contracts.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/services/api.spec.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.vue`
- Modify: `D:/ai-agent/new-local-learn/web/src/components/TaskChatPanel.spec.ts`
- Modify: `D:/ai-agent/new-local-learn/web/src/pages/TaskDetailPage.vue`

- [ ] **Step 1: 写失败测试，断言聊天面板会显示“认知图结论”区域和代码证据区域。**

```ts
expect(wrapper.text()).toContain('认知图结论')
expect(wrapper.text()).toContain('代码证据')
expect(wrapper.text()).toContain('前端组件 -> API 调用 -> 后端路由')
```

- [ ] **Step 2: 运行前端测试，确认当前界面未渲染认知图命中信息。**

Run: `npm test -- --run src/components/TaskChatPanel.spec.ts src/services/api.spec.ts`
Expected: FAIL with missing graph evidence rendering

- [ ] **Step 3: 扩展前端契约和聊天面板，分开展示认知图结论、回答来源和代码证据。**

```ts
export interface TaskGraphEvidence {
  kind: 'entrypoint' | 'symbol' | 'edge' | 'call_chain'
  label: string
  detail?: string | null
  path?: string | null
}
```

```vue
<div v-if="message.graph_evidence.length" class="task-chat__graph">
  <h4>认知图结论</h4>
</div>
```

- [ ] **Step 4: 重新运行前端测试，确认通过。**

Run: `npm test -- --run src/components/TaskChatPanel.spec.ts src/services/api.spec.ts src/pages/TaskDetailPage.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/types/contracts.ts web/src/services/api.spec.ts web/src/components/TaskChatPanel.vue web/src/components/TaskChatPanel.spec.ts web/src/pages/TaskDetailPage.vue
git commit -m "feat: render repo map evidence in chat panel"
```

## Task 8: 回归验证与文档

**Files:**
- Modify: `D:/ai-agent/new-local-learn/README.md`

- [ ] **Step 1: 运行后端目标测试。**

Run: `python -m pytest tests/unit/test_bootstrap.py tests/unit/test_knowledge_store.py tests/unit/test_knowledge_index_builder.py tests/unit/test_repo_map_builder.py tests/unit/test_question_planner.py tests/unit/test_knowledge_chat_service.py tests/tasks/test_jobs.py tests/api/test_task_chat_api.py -q`
Expected: PASS

- [ ] **Step 2: 运行前端目标测试。**

Run: `npm test -- --run src/components/TaskStatusCard.spec.ts src/components/TaskEventTimeline.spec.ts src/components/TaskChatPanel.spec.ts src/pages/TaskDetailPage.spec.ts src/services/api.spec.ts src/composables/useTaskStatus.spec.ts src/services/stream.spec.ts`
Expected: PASS

- [ ] **Step 3: 运行前端构建。**

Run: `npm run build`
Expected: build completed successfully

- [ ] **Step 4: 做一轮真实联调，确认“是否存在某能力”“整体调用链”类问题优于方案二。**

Run: 本地提交一个测试仓库任务，提问“项目里是否存在知识库”“前端请求如何到后端”
Expected: 回答同时给出认知图结论与代码证据

- [ ] **Step 5: 在 README 中补充仓库认知图阶段、产物路径、问答增强说明和降级行为。**

```md
- `knowledge.db`: 代码证据层
- `repo_map.json`: 仓库认知层
- 问答顺序：认知图 -> 代码证据 -> 中文回答
```

- [ ] **Step 6: Commit**

```bash
git add README.md docs/superpowers/specs/2026-04-08-solution-three-repo-map-agent-design.md docs/superpowers/plans/2026-04-08-solution-three-repo-map-agent-plan.md
git commit -m "docs: add solution three repo map agent design and plan"
```
