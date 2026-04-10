import pytest

from app.core.chat_models import PlannerMetadata
from app.core.models import TaskChatMessage, TaskChatResponse
from app.services.chat.models import AgentToolCall, AgentObservation


def test_task_chat_response_accepts_planner_metadata():
    response = TaskChatResponse(
        answer="answer",
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
    call = AgentToolCall.model_validate(
        {
            "tool_name": "search_code",
            "arguments": {"query": "login"},
            "reason": "locate file first",
        }
    )
    assert call.name == "search_code"
    assert call.arguments["query"] == "login"


class _DonePlanner:
    async def plan(self, **kwargs):
        from app.services.chat.models import PlannerResult

        return PlannerResult(
            inferred_intent="explain backend entry",
            answer_depth="detailed",
            current_hypothesis="enough evidence already gathered",
            gaps=[],
            ready_to_answer=True,
            tool_call=None,
        )


class _ToolPlanner:
    async def plan(self, **kwargs):
        from app.services.chat.models import PlannerResult

        observations = kwargs["observations"]
        if observations:
            return PlannerResult(
                inferred_intent="trace request path",
                answer_depth="detailed",
                current_hypothesis="have enough evidence",
                gaps=[],
                ready_to_answer=True,
                tool_call=None,
            )
        return PlannerResult(
            inferred_intent="trace request path",
            answer_depth="detailed",
            current_hypothesis="need call chain evidence",
            gaps=["call chain"],
            ready_to_answer=False,
            tool_call=AgentToolCall(
                name="trace_call_chain",
                arguments={"query": "/health"},
                reason="collect call chain first",
            ),
        )


class _StubGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self):
        return [{"name": "trace_call_chain", "description": "trace", "inputSchema": {"type": "object"}}]

    async def call_tool(self, name: str, arguments: dict[str, object]):
        self.calls.append((name, arguments))
        assert name == "trace_call_chain"
        assert arguments == {"query": "/health"}
        return AgentObservation(
            tool_name="trace_call_chain",
            success=True,
            summary="found 1 chain",
            payload={"chains": [{"summary": "web/App.vue -> GET /health -> app/main.py:health"}]},
        )


class _StubAssembler:
    def assemble(self, *, question, planning_source, observations):
        from app.services.chat.models import EvidenceItem, EvidencePack

        chains = [
            EvidenceItem(kind="call_chain", title=chain["summary"], summary=chain["summary"], path="app/main.py")
            for observation in observations
            for chain in observation.payload.get("chains", [])
        ]
        return EvidencePack(
            question=question,
            planning_source=planning_source,
            call_chains=chains,
            citations=[],
            key_findings=[item.summary for item in chains],
        )


class _StubComposer:
    async def compose(self, *, question, evidence_pack, history):
        return {
            "answer": f"backend entry is app/main.py, question={question}",
            "supplemental_notes": [],
            "confidence": "high",
            "answer_source": "local",
        }


class _LlmComposer:
    async def compose(self, *, question, evidence_pack, history):
        return {
            "answer": f"LLM grounded answer for {question}",
            "supplemental_notes": [],
            "confidence": "high",
            "answer_source": "llm",
        }


class _PassValidator:
    async def validate(self, **kwargs):
        return {
            "passed": True,
            "issues": [],
            "retryable": False,
            "should_expand_context": False,
            "confidence_override": None,
        }


class _NeverReadyPlanner:
    async def plan(self, **kwargs):
        from app.services.chat.models import PlannerResult

        return PlannerResult(
            inferred_intent="trace request path",
            answer_depth="detailed",
            current_hypothesis="still need more evidence",
            gaps=["more evidence"],
            ready_to_answer=False,
            tool_call=AgentToolCall(
                name="trace_call_chain",
                arguments={"query": "/health"},
                reason="collect more evidence",
            ),
        )


@pytest.mark.asyncio
async def test_orchestrator_returns_planner_metadata_for_ready_answer():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    orchestrator = TaskChatOrchestrator(
        planning_agent=_DonePlanner(),
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=_StubAssembler(),
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
    )

    response = await orchestrator.answer_question(
        task_id="task-1",
        db_path="tmp.db",
        repo_map_path=None,
        question="where is backend entry",
        history=[],
    )

    assert response.answer == "backend entry is app/main.py, question=where is backend entry"
    assert response.answer_source == "local"
    assert response.planner_metadata is not None
    assert response.planner_metadata.planning_source == "llm"
    assert response.planner_metadata.loop_count == 1
    assert response.planner_metadata.used_tools == []


@pytest.mark.asyncio
async def test_orchestrator_executes_tool_loop_and_records_used_tools():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    gateway = _StubGateway()
    orchestrator = TaskChatOrchestrator(
        planning_agent=_ToolPlanner(),
        fallback_planner=None,
        mcp_gateway=gateway,
        evidence_assembler=_StubAssembler(),
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
    )

    response = await orchestrator.answer_question(
        task_id="task-2",
        db_path="tmp.db",
        repo_map_path=None,
        question="how does frontend reach backend",
        history=[TaskChatMessage(message_id="u-1", role="user", content="trace it")],
    )

    assert response.planner_metadata is not None
    assert response.planner_metadata.loop_count == 2
    assert response.planner_metadata.used_tools == ["trace_call_chain"]
    assert response.graph_evidence
    assert response.graph_evidence[0].kind == "call_chain"
    assert gateway.calls == [("trace_call_chain", {"query": "/health"})]
    assert response.answer_source == "local"


@pytest.mark.asyncio
async def test_orchestrator_does_not_execute_unfollowable_tool_call_at_loop_limit():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    gateway = _StubGateway()
    orchestrator = TaskChatOrchestrator(
        planning_agent=_NeverReadyPlanner(),
        fallback_planner=None,
        mcp_gateway=gateway,
        evidence_assembler=_StubAssembler(),
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
        max_loops=1,
    )

    response = await orchestrator.answer_question(
        task_id="task-3",
        db_path="tmp.db",
        repo_map_path=None,
        question="how does frontend reach backend",
        history=[],
    )

    assert response.planner_metadata is not None
    assert response.planner_metadata.loop_count == 1
    assert response.planner_metadata.used_tools == []
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_orchestrator_uses_composer_answer_source_when_llm_answer_is_generated():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    orchestrator = TaskChatOrchestrator(
        planning_agent=_DonePlanner(),
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=_StubAssembler(),
        answer_composer=_LlmComposer(),
        answer_validator=_PassValidator(),
    )

    response = await orchestrator.answer_question(
        task_id="task-4",
        db_path="tmp.db",
        repo_map_path=None,
        question="where is backend entry",
        history=[],
    )

    assert response.answer_source == "llm"
