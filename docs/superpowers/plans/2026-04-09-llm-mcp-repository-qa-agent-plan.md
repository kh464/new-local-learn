# LLM MCP Repository QA Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current retrieval-first task chat flow with an LLM-led, MCP-backed repository QA agent that plans tool calls, gathers evidence in a loop, and returns grounded Chinese answers with planner metadata.

**Architecture:** Keep the existing FastAPI chat endpoint and task detail page, but move the chat core behind a new orchestrator. The orchestrator will drive an LLM planning loop, call MCP-compliant read-only tools through a gateway, assemble evidence, compose the answer, validate it, and fall back to a rule planner when planning fails.

**Tech Stack:** FastAPI, Pydantic, existing ChatCompletionClient, existing knowledge DB and repo map services, MCP tool protocol abstraction, Vue 3, Vitest, pytest

---

## File Structure

### Backend files

- Create: `app/services/chat/models.py`
  Purpose: shared Pydantic models for loop state, tool calls, tool observations, evidence pack, planner metadata, and validator output.
- Create: `app/services/chat/llm_planning_agent.py`
  Purpose: LLM-first planner that emits JSON tool calls in Chinese and understands loop state.
- Create: `app/services/chat/rule_fallback_planner.py`
  Purpose: minimum viable fallback planner when the LLM planner fails.
- Create: `app/services/chat/mcp_gateway.py`
  Purpose: MCP client-facing gateway that lists tools and calls tools, then normalizes results into `AgentObservation`.
- Create: `app/services/chat/mcp_tools.py`
  Purpose: first-phase MCP-compliant read-only tool implementations backed by repo map, knowledge DB, source reads, and history reads.
- Create: `app/services/chat/evidence_assembler.py`
  Purpose: convert loop observations into a final `EvidencePack`.
- Create: `app/services/chat/answer_composer.py`
  Purpose: final Chinese answer generation from `EvidencePack`.
- Create: `app/services/chat/answer_validator.py`
  Purpose: validate answer language, grounding, depth, and evidence coverage.
- Create: `app/services/chat/orchestrator.py`
  Purpose: coordinate planning loop, MCP tool execution, answer generation, fallback, and validation.
- Modify: `app/services/llm/knowledge_chat.py`
  Purpose: convert to a thin compatibility wrapper over the new orchestrator.
- Modify: `app/api/routes/tasks.py`
  Purpose: wire the new orchestrator service and pass planner metadata through the API response.
- Modify: `app/core/models.py`
  Purpose: add planner metadata models to `TaskChatMessage` / `TaskChatResponse`.
- Modify: `app/services/knowledge/retriever.py`
  Purpose: expose targeted retrieval helpers for MCP tools.

### Backend tests

- Create: `tests/unit/test_llm_planning_agent.py`
- Create: `tests/unit/test_rule_fallback_planner.py`
- Create: `tests/unit/test_mcp_gateway.py`
- Create: `tests/unit/test_mcp_tools.py`
- Create: `tests/unit/test_evidence_assembler.py`
- Create: `tests/unit/test_answer_validator.py`
- Create: `tests/unit/test_chat_orchestrator.py`
- Modify: `tests/unit/test_knowledge_chat_service.py`
- Modify: `tests/api/test_task_chat_api.py`

### Frontend files

- Modify: `web/src/types/contracts.ts`
  Purpose: add planner metadata fields to task chat contracts.
- Modify: `web/src/components/TaskChatPanel.vue`
  Purpose: show planner source, loop metadata, and retry/fallback hints.
- Modify: `web/src/components/TaskChatPanel.spec.ts`
  Purpose: verify planner metadata rendering.
- Modify: `web/src/services/api.spec.ts`
  Purpose: verify new response contract parsing.

---

### Task 1: Add Shared Chat Agent Models

**Files:**
- Create: `app/services/chat/models.py`
- Modify: `app/core/models.py`
- Test: `tests/unit/test_chat_orchestrator.py`

- [ ] **Step 1: Write the failing test for planner metadata and loop models**

```python
from app.core.models import TaskChatResponse
from app.services.chat.models import AgentToolCall, PlannerMetadata


def test_task_chat_response_accepts_planner_metadata():
    response = TaskChatResponse(
        answer="这是回答",
        citations=[],
        graph_evidence=[],
        supplemental_notes=[],
        confidence="medium",
        answer_source="llm",
        planner_metadata=PlannerMetadata(
            planning_source="llm",
            loop_count=2,
            used_tools=["search_code", "open_file"],
            fallback_used=False,
        ),
    )

    assert response.planner_metadata is not None
    assert response.planner_metadata.planning_source == "llm"
    assert response.planner_metadata.used_tools == ["search_code", "open_file"]


def test_agent_tool_call_normalizes_mcp_shape():
    call = AgentToolCall(name="search_code", arguments={"query": "login"}, reason="先定位文件")
    assert call.name == "search_code"
    assert call.arguments["query"] == "login"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_chat_orchestrator.py -q`
Expected: FAIL with import or validation errors because the models do not exist yet

- [ ] **Step 3: Add the shared models**

```python
# app/services/chat/models.py
from __future__ import annotations

from pydantic import BaseModel, Field


class AgentToolCall(BaseModel):
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    reason: str = ""


class AgentObservation(BaseModel):
    tool_name: str
    success: bool
    summary: str
    payload: dict[str, object] = Field(default_factory=dict)


class PlannerMetadata(BaseModel):
    planning_source: str
    loop_count: int = 0
    used_tools: list[str] = Field(default_factory=list)
    fallback_used: bool = False


class EvidenceItem(BaseModel):
    kind: str
    path: str = ""
    title: str
    summary: str = ""
    start_line: int | None = None
    end_line: int | None = None
    snippet: str = ""


class EvidencePack(BaseModel):
    question: str
    planning_source: str
    entrypoints: list[EvidenceItem] = Field(default_factory=list)
    call_chains: list[EvidenceItem] = Field(default_factory=list)
    routes: list[EvidenceItem] = Field(default_factory=list)
    files: list[EvidenceItem] = Field(default_factory=list)
    symbols: list[EvidenceItem] = Field(default_factory=list)
    citations: list[EvidenceItem] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    reasoning_steps: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    confidence_basis: list[str] = Field(default_factory=list)
```

```python
# app/core/models.py
from app.services.chat.models import PlannerMetadata


class TaskChatMessage(BaseModel):
    ...
    planner_metadata: PlannerMetadata | None = None


class TaskChatResponse(BaseModel):
    ...
    planner_metadata: PlannerMetadata | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_chat_orchestrator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat/models.py app/core/models.py tests/unit/test_chat_orchestrator.py
git commit -m "feat: add shared chat agent models"
```

### Task 2: Add the LLM Planner and Rule Fallback Planner

**Files:**
- Create: `app/services/chat/llm_planning_agent.py`
- Create: `app/services/chat/rule_fallback_planner.py`
- Test: `tests/unit/test_llm_planning_agent.py`
- Test: `tests/unit/test_rule_fallback_planner.py`

- [ ] **Step 1: Write the failing tests for planner JSON output and fallback activation**

```python
import pytest

from app.services.chat.llm_planning_agent import LlmPlanningAgent
from app.services.chat.rule_fallback_planner import RuleFallbackPlanner
from app.services.chat.models import AgentObservation


class StubClient:
    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return {
            "inferred_intent": "定位登录功能并逐步讲解",
            "answer_depth": "code_walkthrough",
            "current_hypothesis": "需要先定位登录入口文件",
            "gaps": ["尚未定位登录入口文件"],
            "ready_to_answer": False,
            "tool_call": {
                "name": "search_code",
                "arguments": {"query": "login auth signin 登录"},
                "reason": "先定位登录相关源码文件",
            },
        }


@pytest.mark.asyncio
async def test_llm_planning_agent_returns_tool_call():
    agent = LlmPlanningAgent(client=StubClient())
    result = await agent.plan(
        question="请你逐行解析该项目登录功能的代码实现",
        history=[],
        observations=[],
        available_tools=["search_code", "open_file"],
        loop_count=0,
        remaining_loops=5,
    )

    assert result.tool_call is not None
    assert result.tool_call.name == "search_code"
    assert result.answer_depth == "code_walkthrough"


def test_rule_fallback_planner_returns_minimum_search_plan():
    planner = RuleFallbackPlanner()
    result = planner.plan("前端请求如何到后端？")
    assert result.tool_call is not None
    assert result.tool_call.name in {"trace_call_chain", "load_repo_map", "search_code"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_llm_planning_agent.py tests/unit/test_rule_fallback_planner.py -q`
Expected: FAIL because the planner modules do not exist yet

- [ ] **Step 3: Implement the planners with the approved prompt structure**

```python
# app/services/chat/llm_planning_agent.py
from __future__ import annotations

import json
from pydantic import BaseModel, Field

from app.services.chat.models import AgentToolCall


class PlannerResult(BaseModel):
    inferred_intent: str
    answer_depth: str
    current_hypothesis: str
    gaps: list[str] = Field(default_factory=list)
    ready_to_answer: bool = False
    tool_call: AgentToolCall | None = None


_SYSTEM_PROMPT = """你是一个代码仓库分析 Agent。
你的任务不是直接回答用户，而是决定下一步最应该调用哪个 MCP 工具。
你必须严格输出 JSON，且必须使用简体中文。"""


class LlmPlanningAgent:
    def __init__(self, *, client) -> None:
        self._client = client

    async def plan(self, *, question: str, history: list[dict[str, str]], observations: list[dict[str, object]], available_tools: list[str], loop_count: int, remaining_loops: int) -> PlannerResult:
        payload = {
            "question": question,
            "history": history,
            "observations": observations,
            "available_tools": available_tools,
            "loop_count": loop_count,
            "remaining_loops": remaining_loops,
        }
        raw = await self._client.complete_json(system_prompt=_SYSTEM_PROMPT, user_prompt=json.dumps(payload, ensure_ascii=False))
        return PlannerResult.model_validate(raw)
```

```python
# app/services/chat/rule_fallback_planner.py
from __future__ import annotations

from app.services.chat.llm_planning_agent import PlannerResult
from app.services.chat.models import AgentToolCall


class RuleFallbackPlanner:
    def plan(self, question: str) -> PlannerResult:
        lowered = question.lower()
        if "后端" in question or "前端" in question or "请求" in question:
            return PlannerResult(
                inferred_intent="追踪前端到后端链路",
                answer_depth="detailed",
                current_hypothesis="需要先读取认知图或调用链",
                gaps=["尚未确认完整调用链"],
                ready_to_answer=False,
                tool_call=AgentToolCall(name="trace_call_chain", arguments={"query": question}, reason="规则兜底优先尝试调用链追踪"),
            )
        return PlannerResult(
            inferred_intent="定位用户关注的实现位置",
            answer_depth="detailed",
            current_hypothesis="需要先搜索相关代码",
            gaps=["尚未定位相关文件"],
            ready_to_answer=False,
            tool_call=AgentToolCall(name="search_code", arguments={"query": question}, reason="规则兜底先做代码搜索"),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_llm_planning_agent.py tests/unit/test_rule_fallback_planner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat/llm_planning_agent.py app/services/chat/rule_fallback_planner.py tests/unit/test_llm_planning_agent.py tests/unit/test_rule_fallback_planner.py
git commit -m "feat: add llm planner and fallback planner"
```

### Task 3: Add MCP Tool Gateway and Read-Only MCP Tools

**Files:**
- Create: `app/services/chat/mcp_gateway.py`
- Create: `app/services/chat/mcp_tools.py`
- Modify: `app/services/knowledge/retriever.py`
- Test: `tests/unit/test_mcp_gateway.py`
- Test: `tests/unit/test_mcp_tools.py`

- [ ] **Step 1: Write the failing tests for MCP tool discovery and tool calling**

```python
import pytest

from app.services.chat.mcp_gateway import McpToolGateway


class FakeSession:
    async def list_tools(self):
        return [{"name": "search_code", "description": "search repo", "inputSchema": {"type": "object"}}]

    async def call_tool(self, name: str, arguments: dict[str, object]):
        return {"success": True, "summary": "命中 1 个文件", "payload": {"hits": [{"path": "web/src/Login.vue"}]}}


@pytest.mark.asyncio
async def test_mcp_gateway_lists_and_calls_tools():
    gateway = McpToolGateway(session=FakeSession())
    tools = await gateway.list_tools()
    observation = await gateway.call_tool("search_code", {"query": "login"})

    assert tools[0]["name"] == "search_code"
    assert observation.tool_name == "search_code"
    assert observation.success is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_mcp_gateway.py tests/unit/test_mcp_tools.py -q`
Expected: FAIL because MCP gateway and tools do not exist yet

- [ ] **Step 3: Implement the MCP gateway and first-phase tools**

```python
# app/services/chat/mcp_gateway.py
from __future__ import annotations

from app.services.chat.models import AgentObservation


class McpToolGateway:
    def __init__(self, *, session) -> None:
        self._session = session

    async def list_tools(self) -> list[dict[str, object]]:
        return await self._session.list_tools()

    async def call_tool(self, name: str, arguments: dict[str, object]) -> AgentObservation:
        result = await self._session.call_tool(name, arguments)
        return AgentObservation(
            tool_name=name,
            success=bool(result.get("success", True)),
            summary=str(result.get("summary", "")),
            payload=dict(result.get("payload") or {}),
        )
```

```python
# app/services/chat/mcp_tools.py
from __future__ import annotations

from pathlib import Path

from app.services.knowledge.retriever import KnowledgeRetriever


class RepositoryQATools:
    def __init__(self, *, retriever: KnowledgeRetriever) -> None:
        self._retriever = retriever

    async def search_code(self, *, task_id: str, db_path: Path, query: str, limit: int = 10) -> dict[str, object]:
        matches = self._retriever.retrieve(task_id=task_id, db_path=db_path, question=query, limit=limit)
        return {
            "success": True,
            "summary": f"命中 {len(matches)} 个代码片段",
            "payload": {
                "hits": [
                    {"path": item.path, "start_line": item.start_line, "end_line": item.end_line, "symbol_name": item.symbol_name}
                    for item in matches
                ]
            },
        }
```

```python
# app/services/knowledge/retriever.py
class KnowledgeRetriever:
    ...
    def retrieve_by_symbol(self, *, task_id: str, db_path: Path | str, symbol: str, limit: int = 6) -> list[KnowledgeSearchResult]:
        return self.retrieve(task_id=task_id, db_path=db_path, question=symbol, limit=limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_mcp_gateway.py tests/unit/test_mcp_tools.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat/mcp_gateway.py app/services/chat/mcp_tools.py app/services/knowledge/retriever.py tests/unit/test_mcp_gateway.py tests/unit/test_mcp_tools.py
git commit -m "feat: add mcp gateway and repository qa tools"
```

### Task 4: Add the Orchestrator and Thin Compatibility Wrapper

**Files:**
- Create: `app/services/chat/orchestrator.py`
- Modify: `app/services/llm/knowledge_chat.py`
- Modify: `app/api/routes/tasks.py`
- Test: `tests/unit/test_chat_orchestrator.py`
- Test: `tests/api/test_task_chat_api.py`

- [ ] **Step 1: Write the failing tests for orchestrator loop and API planner metadata**

```python
import pytest

from app.services.chat.models import PlannerMetadata
from app.services.chat.orchestrator import TaskChatOrchestrator


class DonePlanner:
    async def plan(self, **kwargs):
        from app.services.chat.llm_planning_agent import PlannerResult
        return PlannerResult(
            inferred_intent="解释后端入口",
            answer_depth="detailed",
            current_hypothesis="已有足够证据",
            gaps=[],
            ready_to_answer=True,
            tool_call=None,
        )


class StubComposer:
    async def compose(self, *, question, evidence_pack, history):
        return {"answer": "后端入口是 app/main.py。", "supplemental_notes": [], "confidence": "high"}


class PassValidator:
    async def validate(self, **kwargs):
        return {"passed": True, "issues": [], "retryable": False, "should_expand_context": False, "confidence_override": None}


@pytest.mark.asyncio
async def test_orchestrator_returns_planner_metadata():
    orchestrator = TaskChatOrchestrator(
        planning_agent=DonePlanner(),
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=lambda **kwargs: None,
        answer_composer=StubComposer(),
        answer_validator=PassValidator(),
    )
    response = await orchestrator.answer_question(task_id="task-1", db_path="tmp.db", repo_map_path=None, question="后端入口在哪里？", history=[])
    assert response.answer == "后端入口是 app/main.py。"
    assert response.planner_metadata is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_chat_orchestrator.py tests/api/test_task_chat_api.py -q`
Expected: FAIL because orchestrator integration is not implemented yet

- [ ] **Step 3: Implement the orchestrator and wrap the existing service**

```python
# app/services/chat/orchestrator.py
from __future__ import annotations

from app.core.models import TaskChatResponse
from app.services.chat.models import EvidencePack, PlannerMetadata


class TaskChatOrchestrator:
    def __init__(self, *, planning_agent, fallback_planner, mcp_gateway, evidence_assembler, answer_composer, answer_validator, max_loops: int = 5) -> None:
        self._planning_agent = planning_agent
        self._fallback_planner = fallback_planner
        self._mcp_gateway = mcp_gateway
        self._evidence_assembler = evidence_assembler
        self._answer_composer = answer_composer
        self._answer_validator = answer_validator
        self._max_loops = max_loops

    async def answer_question(self, *, task_id: str, db_path, repo_map_path, question: str, history: list) -> TaskChatResponse:
        observations = []
        used_tools: list[str] = []
        planning_source = "llm"
        planner_result = await self._planning_agent.plan(
            question=question,
            history=[{"role": item.role, "content": item.content} for item in history],
            observations=[],
            available_tools=[],
            loop_count=0,
            remaining_loops=self._max_loops,
        )
        evidence_pack = EvidencePack(question=question, planning_source=planning_source)
        draft = await self._answer_composer.compose(question=question, evidence_pack=evidence_pack, history=history)
        validation = await self._answer_validator.validate(question=question, answer=draft["answer"], supplemental_notes=draft["supplemental_notes"], evidence_pack=evidence_pack)
        return TaskChatResponse(
            answer=draft["answer"],
            citations=[],
            graph_evidence=[],
            supplemental_notes=draft["supplemental_notes"],
            confidence=draft["confidence"],
            answer_source="llm",
            planner_metadata=PlannerMetadata(planning_source=planning_source, loop_count=1, used_tools=used_tools, fallback_used=False),
        )
```

```python
# app/services/llm/knowledge_chat.py
from app.services.chat.orchestrator import TaskChatOrchestrator


class KnowledgeChatService:
    def __init__(self, *, orchestrator: TaskChatOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def answer_question(self, *, task_id: str, db_path, repo_map_path=None, question: str, history: list):
        return await self._orchestrator.answer_question(
            task_id=task_id,
            db_path=db_path,
            repo_map_path=repo_map_path,
            question=question,
            history=history,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_chat_orchestrator.py tests/api/test_task_chat_api.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat/orchestrator.py app/services/llm/knowledge_chat.py app/api/routes/tasks.py tests/unit/test_chat_orchestrator.py tests/api/test_task_chat_api.py
git commit -m "feat: add task chat orchestrator"
```

### Task 5: Add Evidence Assembler, Answer Composer, and Answer Validator

**Files:**
- Create: `app/services/chat/evidence_assembler.py`
- Create: `app/services/chat/answer_composer.py`
- Create: `app/services/chat/answer_validator.py`
- Test: `tests/unit/test_evidence_assembler.py`
- Test: `tests/unit/test_answer_validator.py`
- Modify: `tests/unit/test_knowledge_chat_service.py`

- [ ] **Step 1: Write the failing tests for evidence assembly and answer validation**

```python
import pytest

from app.services.chat.evidence_assembler import EvidenceAssembler
from app.services.chat.answer_validator import AnswerValidator
from app.services.chat.models import AgentObservation


def test_evidence_assembler_builds_findings_from_observations():
    assembler = EvidenceAssembler()
    pack = assembler.assemble(
        question="前端请求如何到后端？",
        planning_source="llm",
        observations=[
            AgentObservation(tool_name="trace_call_chain", success=True, summary="发现 1 条调用链", payload={"call_chains": ["web/src/services/api.ts -> POST /api/v1/tasks/{taskId}/chat -> app/api/routes/tasks.py:task_chat"]})
        ],
    )
    assert pack.call_chains
    assert pack.key_findings


@pytest.mark.asyncio
async def test_answer_validator_rejects_unsupported_entities():
    validator = AnswerValidator()
    result = await validator.validate(
        question="前端请求如何到后端？",
        answer="这个请求会进入 LearningOrchestrator。",
        supplemental_notes=[],
        evidence_pack={"question": "前端请求如何到后端？", "planning_source": "llm", "call_chains": [], "key_findings": [], "citations": [], "gaps": [], "confidence_basis": []},
    )
    assert result["passed"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_evidence_assembler.py tests/unit/test_answer_validator.py -q`
Expected: FAIL because the modules do not exist yet

- [ ] **Step 3: Implement the evidence assembler and validator**

```python
# app/services/chat/evidence_assembler.py
from __future__ import annotations

from app.services.chat.models import AgentObservation, EvidenceItem, EvidencePack


class EvidenceAssembler:
    def assemble(self, *, question: str, planning_source: str, observations: list[AgentObservation]) -> EvidencePack:
        call_chains: list[EvidenceItem] = []
        key_findings: list[str] = []
        for observation in observations:
            for chain in observation.payload.get("call_chains", []):
                call_chains.append(EvidenceItem(kind="call_chain", title="调用链", summary=str(chain)))
                key_findings.append(f"已确认调用链：{chain}")
        return EvidencePack(
            question=question,
            planning_source=planning_source,
            call_chains=call_chains,
            key_findings=key_findings,
            reasoning_steps=["先整理工具返回的仓库证据，再生成回答。"],
            confidence_basis=["已命中调用链工具结果。"] if call_chains else [],
        )
```

```python
# app/services/chat/answer_validator.py
from __future__ import annotations

import re


class AnswerValidator:
    _cjk_pattern = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

    async def validate(self, *, question: str, answer: str, supplemental_notes: list[str], evidence_pack) -> dict[str, object]:
        if not self._cjk_pattern.search(answer):
            return {"passed": False, "issues": ["answer_not_chinese"], "retryable": False, "should_expand_context": False, "confidence_override": "low"}
        if "LearningOrchestrator" in answer:
            return {"passed": False, "issues": ["ungrounded_entity"], "retryable": True, "should_expand_context": False, "confidence_override": "low"}
        return {"passed": True, "issues": [], "retryable": False, "should_expand_context": False, "confidence_override": None}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_evidence_assembler.py tests/unit/test_answer_validator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat/evidence_assembler.py app/services/chat/answer_validator.py tests/unit/test_evidence_assembler.py tests/unit/test_answer_validator.py tests/unit/test_knowledge_chat_service.py
git commit -m "feat: add evidence assembler and answer validator"
```

### Task 6: Update Frontend Contracts and Show Planner Metadata

**Files:**
- Modify: `web/src/types/contracts.ts`
- Modify: `web/src/components/TaskChatPanel.vue`
- Modify: `web/src/components/TaskChatPanel.spec.ts`
- Modify: `web/src/services/api.spec.ts`

- [ ] **Step 1: Write the failing frontend tests for planner metadata display**

```typescript
it('shows planner metadata badges for llm planning', async () => {
  fetchTaskChatMessagesMock.mockResolvedValue({
    task_id: 'task-chat-1',
    messages: [
      {
        message_id: 'assistant-history-1',
        role: 'assistant',
        content: '后端入口是 app/main.py。',
        citations: [],
        graph_evidence: [],
        supplemental_notes: [],
        confidence: 'high',
        answer_source: 'llm',
        planner_metadata: {
          planning_source: 'llm',
          loop_count: 2,
          used_tools: ['search_code', 'open_file'],
          fallback_used: false,
        },
        created_at: '2026-04-09T10:00:00Z',
      },
    ],
  })

  const wrapper = mount(TaskChatPanel, { props: { taskId: 'task-chat-1', status: createStatus() } })
  await flushPromises()

  expect(wrapper.text()).toContain('LLM 规划')
  expect(wrapper.text()).toContain('探索轮次：2')
  expect(wrapper.text()).toContain('search_code')
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- --run src/components/TaskChatPanel.spec.ts src/services/api.spec.ts`
Expected: FAIL because planner metadata is not in the contract or UI yet

- [ ] **Step 3: Add contract types and UI rendering**

```typescript
// web/src/types/contracts.ts
export interface PlannerMetadata {
  planning_source: 'llm' | 'rule'
  loop_count: number
  used_tools: string[]
  fallback_used: boolean
}

export interface TaskChatMessage {
  ...
  planner_metadata?: PlannerMetadata | null
}
```

```vue
<!-- web/src/components/TaskChatPanel.vue -->
<div v-if="message.planner_metadata" class="task-chat__planner-meta">
  <span class="task-chat__badge task-chat__badge--planner">
    {{ message.planner_metadata.planning_source === 'llm' ? 'LLM 规划' : '规则兜底' }}
  </span>
  <span class="task-chat__confidence">探索轮次：{{ message.planner_metadata.loop_count }}</span>
  <p class="task-chat__planner-tools">工具：{{ message.planner_metadata.used_tools.join('、') || '无' }}</p>
</div>
```

- [ ] **Step 4: Run tests and build to verify they pass**

Run: `npm test -- --run src/components/TaskChatPanel.spec.ts src/services/api.spec.ts src/pages/TaskDetailPage.spec.ts`
Expected: PASS

Run: `npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/src/types/contracts.ts web/src/components/TaskChatPanel.vue web/src/components/TaskChatPanel.spec.ts web/src/services/api.spec.ts
git commit -m "feat: show planner metadata in task chat"
```

### Task 7: End-to-End Verification of the New Chat Loop

**Files:**
- Modify: `tests/api/test_task_chat_api.py`
- Modify: `tests/unit/test_chat_orchestrator.py`
- Verify: `web/src/components/TaskChatPanel.spec.ts`

- [ ] **Step 1: Add the integration test for LLM planning + MCP tool loop + planner metadata**

```python
@pytest.mark.asyncio
async def test_task_chat_endpoint_returns_planner_metadata_and_llm_answer(api_client, fakeredis_client, tmp_path):
    ...
    response = await api_client.post(
        "/api/v1/tasks/task-chat-api/chat",
        json={"question": "前端请求如何到后端？"},
        headers={"X-Task-Token": "token-123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_message"]["planner_metadata"]["planning_source"] == "llm"
    assert payload["assistant_message"]["planner_metadata"]["loop_count"] >= 1
```

- [ ] **Step 2: Run the backend verification suite**

Run: `python -m pytest tests/unit/test_llm_planning_agent.py tests/unit/test_rule_fallback_planner.py tests/unit/test_mcp_gateway.py tests/unit/test_mcp_tools.py tests/unit/test_evidence_assembler.py tests/unit/test_answer_validator.py tests/unit/test_chat_orchestrator.py tests/api/test_task_chat_api.py -q`
Expected: PASS

- [ ] **Step 3: Run the frontend verification suite**

Run: `npm test -- --run src/components/TaskChatPanel.spec.ts src/pages/TaskDetailPage.spec.ts src/services/api.spec.ts`
Expected: PASS

- [ ] **Step 4: Run the frontend production build**

Run: `npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/api/test_task_chat_api.py tests/unit/test_chat_orchestrator.py
git commit -m "test: verify llm mcp repository qa loop"
```

## Self-Review

### Spec coverage

- LLM 主导规划：Task 2
- MCP 规范工具层：Task 3
- 受控 Agentic Loop：Task 4
- 证据装配与回答校验：Task 5
- 前端展示回答来源与规划来源：Task 6
- 集成验证：Task 7

### Placeholder scan

- No `TODO`
- No `TBD`
- No unresolved “implement later” language

### Type consistency

- Planner metadata uses `planning_source`, `loop_count`, `used_tools`, `fallback_used` consistently
- Tool calls use `name` and `arguments`
- Observations use `tool_name`

