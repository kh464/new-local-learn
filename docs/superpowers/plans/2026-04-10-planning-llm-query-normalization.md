# Planning LLM Query Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stabilize the planning LLM so semantically equivalent repository questions produce similar retrieval plans and code search inputs.

**Architecture:** Extend the planner result with normalized query fields, strengthen the planning system prompt so the LLM explicitly canonicalizes user intent before choosing tools, and make the orchestrator prefer these normalized retrieval terms when invoking search tools. Keep the answer stage unchanged.

**Tech Stack:** Python, Pydantic, pytest, existing chat orchestrator and planning agent.

---

### Task 1: Add planner result fields for normalized retrieval intent

**Files:**
- Modify: `app/services/chat/models.py`
- Test: `tests/unit/test_llm_planning_agent.py`

- [ ] **Step 1: Write the failing test**

```python
assert result.normalized_question == "确认仓库是否实现知识库能力"
assert result.retrieval_objective == "定位知识库能力相关实现与入口"
assert result.search_queries == ["知识库", "knowledge", "retriever", "repo_map"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_llm_planning_agent.py -q`
Expected: FAIL because `PlannerResult` does not yet expose the normalized retrieval fields.

- [ ] **Step 3: Write minimal implementation**

```python
class PlannerResult(BaseModel):
    inferred_intent: str
    answer_depth: str
    current_hypothesis: str
    gaps: list[str] = Field(default_factory=list)
    normalized_question: str = ""
    retrieval_objective: str = ""
    search_queries: list[str] = Field(default_factory=list)
    ready_to_answer: bool = False
    tool_call: AgentToolCall | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_llm_planning_agent.py -q`
Expected: PASS for the new normalized field assertions.

- [ ] **Step 5: Commit**

```bash
git add app/services/chat/models.py tests/unit/test_llm_planning_agent.py
git commit -m "feat: add normalized planner query fields"
```

### Task 2: Strengthen the planning prompt and normalize incomplete planner output

**Files:**
- Modify: `app/services/chat/llm_planning_agent.py`
- Test: `tests/unit/test_llm_planning_agent.py`

- [ ] **Step 1: Write the failing test**

```python
assert "normalized_question" in client.last_system_prompt
assert "search_queries" in client.last_system_prompt
assert result.search_queries == ["知识库", "knowledge", "retriever", "repo_map"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_llm_planning_agent.py -q`
Expected: FAIL because the system prompt and result normalization do not yet mention or fill these fields.

- [ ] **Step 3: Write minimal implementation**

```python
result = PlannerResult.model_validate(raw)
result = self._normalize_result(result=result, question=question)

if not result.normalized_question.strip():
    result.normalized_question = question.strip()
if not result.retrieval_objective.strip():
    result.retrieval_objective = result.inferred_intent.strip() or question.strip()
if not result.search_queries:
    result.search_queries = self._build_search_queries(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_llm_planning_agent.py -q`
Expected: PASS with prompt assertions and normalized fallback behavior.

- [ ] **Step 5: Commit**

```bash
git add app/services/chat/llm_planning_agent.py tests/unit/test_llm_planning_agent.py
git commit -m "feat: stabilize llm planning prompts"
```

### Task 3: Make the orchestrator prefer normalized retrieval queries for search tools

**Files:**
- Modify: `app/services/chat/orchestrator.py`
- Test: `tests/unit/test_chat_orchestrator.py`

- [ ] **Step 1: Write the failing test**

```python
assert gateway.calls == [
    ("search_code", {"query": "知识库 knowledge retriever repo_map"})
]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_chat_orchestrator.py -q`
Expected: FAIL because the orchestrator still forwards the raw planner tool arguments unchanged.

- [ ] **Step 3: Write minimal implementation**

```python
arguments = dict(plan.tool_call.arguments)
if plan.tool_call.name == "search_code" and plan.search_queries:
    arguments["query"] = " ".join(plan.search_queries)
observation = await self._mcp_gateway.call_tool(plan.tool_call.name, arguments)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_chat_orchestrator.py -q`
Expected: PASS and the gateway should receive the normalized search query string.

- [ ] **Step 5: Commit**

```bash
git add app/services/chat/orchestrator.py tests/unit/test_chat_orchestrator.py
git commit -m "feat: use normalized planner queries in tool calls"
```

### Task 4: Verify the targeted backend test set

**Files:**
- Test: `tests/unit/test_llm_planning_agent.py`
- Test: `tests/unit/test_chat_orchestrator.py`

- [ ] **Step 1: Run targeted verification**

Run: `pytest tests/unit/test_llm_planning_agent.py tests/unit/test_chat_orchestrator.py -q`
Expected: PASS with 0 failures.

- [ ] **Step 2: Run one planner-adjacent regression file**

Run: `pytest tests/unit/test_rule_fallback_planner.py -q`
Expected: PASS to confirm the rule fallback still works with the expanded planner model.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-04-10-planning-llm-query-normalization.md
git commit -m "docs: add planning llm normalization plan"
```
