import pytest

from app.core.chat_models import PlannerMetadata
from app.core.models import TaskChatMessage, TaskChatResponse
from app.services.chat.question_analyzer import QuestionAnalysis
from app.services.code_graph.graph_expander import ExpandedSubgraph
from app.services.code_graph.models import CodeEdge, CodeFileNode, CodeSnippetEvidence, CodeSymbolNode, RetrievalCandidate
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
            search_queries=["login", "auth"],
        ),
    )

    assert response.planner_metadata is not None
    assert response.planner_metadata.planning_source == "llm"
    assert response.planner_metadata.used_tools == ["search_code", "open_file"]
    assert response.planner_metadata.search_queries == ["login", "auth"]


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


class _SearchGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self):
        return [{"name": "search_code", "description": "search", "inputSchema": {"type": "object"}}]

    async def call_tool(self, name: str, arguments: dict[str, object]):
        self.calls.append((name, arguments))
        assert name == "search_code"
        assert arguments == {"query": "知识库 knowledge retriever repo_map"}
        return AgentObservation(
            tool_name="search_code",
            success=True,
            summary="found knowledge files",
            payload={"hits": [{"path": "app/services/knowledge/retriever.py", "title": "KnowledgeRetriever"}]},
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


class _HybridQuestionAnalyzer:
    async def analyze(self, *, question, history):
        return QuestionAnalysis(
            normalized_question="解释 health 的职责",
            question_type="module_responsibility",
            answer_depth="detailed",
            retrieval_objective="定位 health 函数及其下游调用",
            target_entities=["app.main.health"],
            preferred_item_types=["symbol", "file"],
        )


class _HybridExactRetriever:
    def retrieve(self, **kwargs):
        return [
            RetrievalCandidate(
                task_id="task-hybrid",
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


class _HybridSemanticRetriever:
    async def retrieve(self, **kwargs):
        return [
            RetrievalCandidate(
                task_id="task-hybrid",
                item_id="function:python:app/main.py:app.main.health",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.health",
                qualified_name="app.main.health",
                score=0.88,
                source="semantic",
                summary_zh="该函数负责健康检查入口。",
            )
        ]


class _HybridRanker:
    def rank(self, *, exact_hits, semantic_hits, limit):
        return exact_hits[:1]


class _HybridGraphExpander:
    def expand(self, **kwargs):
        return ExpandedSubgraph(
            seeds=kwargs["seeds"],
            files=[
                CodeFileNode(
                    task_id="task-hybrid",
                    path="app/main.py",
                    language="python",
                    file_kind="source",
                    summary_zh="该文件负责应用入口。",
                    entry_role="backend_entry",
                )
            ],
            symbols=[
                CodeSymbolNode(
                    task_id="task-hybrid",
                    symbol_id="function:python:app/main.py:app.main.health",
                    symbol_kind="function",
                    name="health",
                    qualified_name="app.main.health",
                    file_path="app/main.py",
                    start_line=4,
                    end_line=5,
                    summary_zh="该函数负责健康检查入口。",
                    language="python",
                )
            ],
            edges=[
                CodeEdge(
                    task_id="task-hybrid",
                    from_symbol_id="file:python:app/main.py",
                    to_symbol_id="function:python:app/main.py:app.main.health",
                    edge_kind="contains",
                    source_path="app/main.py",
                    line=4,
                )
            ],
        )


class _HybridCodeLocator:
    def locate(self, *, subgraph):
        return [
            CodeSnippetEvidence(
                path="app/main.py",
                start_line=4,
                end_line=5,
                snippet="def health():\n    return {'ok': True}",
                symbol_id="function:python:app/main.py:app.main.health",
                qualified_name="app.main.health",
            )
        ]


class _HybridEvidenceBuilder:
    def build(self, *, question, normalized_question, retrieval_objective, subgraph, snippets):
        from app.services.code_graph.evidence_builder import EvidencePack

        return EvidencePack(
            question=question,
            normalized_question=normalized_question,
            retrieval_objective=retrieval_objective,
            seeds=subgraph.seeds,
            snippets=snippets,
            graph_nodes=[{"kind": "symbol", "qualified_name": "app.main.health", "path": "app/main.py"}],
            graph_edges=[{"kind": "contains", "from": "file:python:app/main.py", "to": "function:python:app/main.py:app.main.health"}],
            summaries=["该函数负责健康检查入口。"],
        )


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


class _SearchPlanner:
    async def plan(self, **kwargs):
        from app.services.chat.models import PlannerResult

        observations = kwargs["observations"]
        if observations:
            return PlannerResult(
                inferred_intent="确认仓库是否实现知识库能力",
                answer_depth="detailed",
                current_hypothesis="已有足够证据",
                normalized_question="确认仓库是否实现知识库能力",
                retrieval_objective="定位知识库能力相关实现与入口",
                search_queries=["知识库", "knowledge", "retriever", "repo_map"],
                gaps=[],
                ready_to_answer=True,
                tool_call=None,
            )
        return PlannerResult(
            inferred_intent="确认仓库是否实现知识库能力",
            answer_depth="detailed",
            current_hypothesis="需要先定位知识库相关实现",
            normalized_question="确认仓库是否实现知识库能力",
            retrieval_objective="定位知识库能力相关实现与入口",
            search_queries=["知识库", "knowledge", "retriever", "repo_map"],
            gaps=["尚未定位知识库实现"],
            ready_to_answer=False,
            tool_call=AgentToolCall(
                name="search_code",
                arguments={"query": "仓库是否具有知识库"},
                reason="先搜索知识库相关实现",
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
async def test_orchestrator_prefers_normalized_search_queries_for_search_tool():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    gateway = _SearchGateway()
    orchestrator = TaskChatOrchestrator(
        planning_agent=_SearchPlanner(),
        fallback_planner=None,
        mcp_gateway=gateway,
        evidence_assembler=_StubAssembler(),
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
    )

    response = await orchestrator.answer_question(
        task_id="task-search",
        db_path="tmp.db",
        repo_map_path=None,
        question="仓库是否具有具有知识库",
        history=[],
    )

    assert response.planner_metadata is not None
    assert response.planner_metadata.loop_count == 2
    assert response.planner_metadata.used_tools == ["search_code"]
    assert response.planner_metadata.search_queries == ["知识库", "knowledge", "retriever", "repo_map"]
    assert gateway.calls == [("search_code", {"query": "知识库 knowledge retriever repo_map"})]


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


@pytest.mark.asyncio
async def test_orchestrator_prefers_hybrid_graph_pipeline_when_configured():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    orchestrator = TaskChatOrchestrator(
        planning_agent=_DonePlanner(),
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=_StubAssembler(),
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
        question_analyzer=_HybridQuestionAnalyzer(),
        exact_retriever=_HybridExactRetriever(),
        semantic_retriever=_HybridSemanticRetriever(),
        hybrid_ranker=_HybridRanker(),
        graph_expander=_HybridGraphExpander(),
        code_locator=_HybridCodeLocator(),
        graph_evidence_builder=_HybridEvidenceBuilder(),
    )

    response = await orchestrator.answer_question(
        task_id="task-hybrid",
        db_path="tmp.db",
        repo_map_path=None,
        question="health 做了什么",
        history=[TaskChatMessage(message_id="u-1", role="user", content="解释一下")],
    )

    assert response.answer_source == "local"
    assert response.citations
    assert response.citations[0].path == "app/main.py"
    assert response.graph_evidence
    assert response.graph_evidence[0].path == "app/main.py"
    assert response.planner_metadata is not None
    assert response.planner_metadata.planning_source == "hybrid_rag"
    assert response.planner_metadata.used_tools == ["exact_retriever", "semantic_retriever", "graph_expander", "code_locator"]
