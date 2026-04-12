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


class _HistoryAwareComposer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def compose(self, *, question, evidence_pack, history):
        self.calls.append(
            {
                "question": question,
                "history_roles": [item.role for item in history],
                "history_contents": [item.content for item in history],
            }
        )
        return {
            "answer": f"history_count={len(history)}",
            "supplemental_notes": [],
            "confidence": "high",
            "answer_source": "local",
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


class _HistoryAwareQuestionAnalyzer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def analyze(self, *, question, history):
        self.calls.append({"question": question, "history": list(history)})
        return QuestionAnalysis(
            normalized_question=question,
            question_type="module_responsibility",
            answer_depth="detailed",
            retrieval_objective=question,
            target_entities=[],
            preferred_item_types=["symbol", "file"],
            search_queries=["knowledge", "repo_map"],
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
    def rank(self, *, exact_hits, semantic_hits, limit, **kwargs):
        del kwargs
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


class _ArchitectureQuestionAnalyzer:
    async def analyze(self, *, question, history):
        return QuestionAnalysis(
            normalized_question=question,
            question_type="architecture_explanation",
            answer_depth="detailed",
            retrieval_objective=question,
            target_entities=["app.main.enqueue_turn_task"],
            preferred_item_types=["symbol", "file"],
            search_queries=["task_queue.py", "submit"],
        )


class _RecordingGraphExpander:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def expand(self, **kwargs):
        self.calls.append(dict(kwargs))
        return _HybridGraphExpander().expand(**kwargs)


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


@pytest.mark.asyncio
async def test_orchestrator_uses_deeper_graph_hops_for_architecture_questions():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    expander = _RecordingGraphExpander()
    orchestrator = TaskChatOrchestrator(
        planning_agent=_DonePlanner(),
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=_StubAssembler(),
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
        question_analyzer=_ArchitectureQuestionAnalyzer(),
        exact_retriever=_HybridExactRetriever(),
        semantic_retriever=None,
        hybrid_ranker=_HybridRanker(),
        graph_expander=expander,
        code_locator=_HybridCodeLocator(),
        graph_evidence_builder=_HybridEvidenceBuilder(),
    )

    await orchestrator.answer_question(
        task_id="task-hybrid-arch",
        db_path="tmp.db",
        repo_map_path=None,
        question="用户提交分析任务后后端会经过哪些步骤",
        history=[],
    )

    assert expander.calls
    assert expander.calls[0]["max_hops"] == 3


@pytest.mark.asyncio
async def test_orchestrator_clears_unrelated_history_for_new_topic_in_hybrid_pipeline():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    analyzer = _HistoryAwareQuestionAnalyzer()
    composer = _HistoryAwareComposer()
    orchestrator = TaskChatOrchestrator(
        planning_agent=_DonePlanner(),
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=_StubAssembler(),
        answer_composer=composer,
        answer_validator=_PassValidator(),
        question_analyzer=analyzer,
        exact_retriever=_HybridExactRetriever(),
        semantic_retriever=None,
        hybrid_ranker=_HybridRanker(),
        graph_expander=_HybridGraphExpander(),
        code_locator=_HybridCodeLocator(),
        graph_evidence_builder=_HybridEvidenceBuilder(),
    )

    history = [
        TaskChatMessage(message_id="u-1", role="user", content="GET /health 是由哪个函数处理的？"),
        TaskChatMessage(message_id="a-1", role="assistant", content="由 app.main.create_app.health 处理。"),
    ]

    await orchestrator.answer_question(
        task_id="task-history-reset",
        db_path="tmp.db",
        repo_map_path=None,
        question="这个项目里是否实现了知识库能力？请只基于代码证据回答。",
        history=history,
    )

    assert analyzer.calls
    assert analyzer.calls[0]["history"] == []
    assert composer.calls
    assert composer.calls[0]["history_contents"] == []


@pytest.mark.asyncio
async def test_orchestrator_preserves_recent_history_for_followup_question_in_hybrid_pipeline():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    analyzer = _HistoryAwareQuestionAnalyzer()
    composer = _HistoryAwareComposer()
    orchestrator = TaskChatOrchestrator(
        planning_agent=_DonePlanner(),
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=_StubAssembler(),
        answer_composer=composer,
        answer_validator=_PassValidator(),
        question_analyzer=analyzer,
        exact_retriever=_HybridExactRetriever(),
        semantic_retriever=None,
        hybrid_ranker=_HybridRanker(),
        graph_expander=_HybridGraphExpander(),
        code_locator=_HybridCodeLocator(),
        graph_evidence_builder=_HybridEvidenceBuilder(),
    )

    history = [
        TaskChatMessage(message_id="u-1", role="user", content="GET /health 是由哪个函数处理的？"),
        TaskChatMessage(message_id="a-1", role="assistant", content="由 app.main.create_app.health 处理。"),
    ]

    await orchestrator.answer_question(
        task_id="task-history-followup",
        db_path="tmp.db",
        repo_map_path=None,
        question="那它是不是定义在 create_app() 里面？",
        history=history,
    )

    assert analyzer.calls
    assert [item["content"] for item in analyzer.calls[0]["history"]] == [
        "GET /health 是由哪个函数处理的？",
        "由 app.main.create_app.health 处理。",
    ]
    assert composer.calls
    assert composer.calls[0]["history_contents"] == [
        "GET /health 是由哪个函数处理的？",
        "由 app.main.create_app.health 处理。",
    ]


def test_orchestrator_converts_route_graph_evidence_into_structured_chat_evidence():
    from app.services.chat.orchestrator import TaskChatOrchestrator
    from app.services.code_graph.evidence_builder import EvidencePack as GraphEvidencePack
    from app.services.code_graph.models import CodeSnippetEvidence, RetrievalCandidate

    orchestrator = TaskChatOrchestrator(
        planning_agent=None,
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=None,
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
    )

    graph_pack = GraphEvidencePack(
        question="GET /health 是由哪个函数处理的？请给出文件位置。",
        normalized_question="定位 /health 路由处理函数",
        retrieval_objective="定位路由节点与处理函数",
        seeds=[
            RetrievalCandidate(
                task_id="task-hybrid",
                item_id="function:python:app/main.py:app.main.create_app.health",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.create_app.health",
                qualified_name="app.main.create_app.health",
                score=120.0,
                source="exact",
                summary_zh="健康检查处理函数",
            )
        ],
        snippets=[
            CodeSnippetEvidence(
                path="app/main.py",
                start_line=275,
                end_line=278,
                snippet="    @app.get('/health')\n    async def health():\n        return {'status': 'ok'}",
                symbol_id="function:python:app/main.py:app.main.create_app.health",
                qualified_name="app.main.create_app.health",
            )
        ],
        graph_nodes=[
            {
                "kind": "file",
                "path": "app/main.py",
                "summary_zh": "应用入口文件",
                "entry_role": "backend_entry",
            },
            {
                "kind": "route",
                "path": "app/main.py",
                "name": "GET /health",
                "qualified_name": "app.main.create_app.health.__route__.app.get:/health",
                "summary_zh": "健康检查路由",
                "start_line": 274,
                "end_line": 274,
            },
            {
                "kind": "function",
                "path": "app/main.py",
                "name": "health",
                "qualified_name": "app.main.create_app.health",
                "summary_zh": "健康检查处理函数",
                "start_line": 275,
                "end_line": 278,
            },
            {
                "kind": "route",
                "path": "app/main.py",
                "name": "GET /health/ready",
                "qualified_name": "app.main.create_app.health_ready.__route__.app.get:/health/ready",
                "summary_zh": "健康检查就绪路由",
                "start_line": 279,
                "end_line": 279,
            },
            {
                "kind": "function",
                "path": "app/main.py",
                "name": "health_ready",
                "qualified_name": "app.main.create_app.health_ready",
                "summary_zh": "健康检查就绪处理函数",
                "start_line": 280,
                "end_line": 283,
            },
        ],
        graph_edges=[
            {
                "kind": "contains",
                "from": "file:python:app/main.py",
                "to": "route:python:app/main.py:app.main.create_app.health.__route__.app.get:/health",
                "path": "app/main.py",
                "line": 274,
            },
            {
                "kind": "routes_to",
                "from": "route:python:app/main.py:app.main.create_app.health.__route__.app.get:/health",
                "to": "function:python:app/main.py:app.main.create_app.health",
                "path": "app/main.py",
                "line": 274,
            },
            {
                "kind": "routes_to",
                "from": "route:python:app/main.py:app.main.create_app.health_ready.__route__.app.get:/health/ready",
                "to": "function:python:app/main.py:app.main.create_app.health_ready",
                "path": "app/main.py",
                "line": 279,
            },
        ],
        summaries=["命中了 /health 路由及其处理函数。"],
    )

    evidence_pack = orchestrator._convert_graph_evidence(graph_pack)

    assert evidence_pack.entrypoints
    assert evidence_pack.entrypoints[0].path == "app/main.py"
    assert evidence_pack.routes
    assert evidence_pack.routes[0].title == "GET /health"
    assert evidence_pack.routes[0].start_line == 274
    assert evidence_pack.call_chains
    assert evidence_pack.call_chains[0].title == "GET /health -> app.main.create_app.health"
    assert evidence_pack.call_chains[0].summary.startswith("路由 GET /health")
    assert evidence_pack.symbols[0].title == "app.main.create_app.health"
    assert evidence_pack.key_findings[0] == "已确认 GET /health 由 app.main.create_app.health 处理，函数位置在 app/main.py:275。"
    assert any("属于 create_app 的内部符号作用域" in item for item in evidence_pack.key_findings)
    assert any("app/main.py" in item for item in evidence_pack.key_findings)


def test_orchestrator_prioritizes_route_matching_question_when_seed_is_only_file_level():
    from app.services.chat.orchestrator import TaskChatOrchestrator
    from app.services.code_graph.evidence_builder import EvidencePack as GraphEvidencePack
    from app.services.code_graph.models import RetrievalCandidate

    orchestrator = TaskChatOrchestrator(
        planning_agent=None,
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=None,
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
    )

    graph_pack = GraphEvidencePack(
        question="GET /health 是由哪个函数处理的？",
        normalized_question="定位 /health 路由处理函数",
        retrieval_objective="定位路由节点与处理函数",
        seeds=[
            RetrievalCandidate(
                task_id="task-hybrid",
                item_id="file:python:app/main.py",
                item_type="file",
                path="app/main.py",
                symbol_id=None,
                qualified_name=None,
                score=100.0,
                source="exact",
                summary_zh="后端入口文件",
            )
        ],
        graph_nodes=[
            {"kind": "file", "path": "app/main.py", "summary_zh": "应用入口文件", "entry_role": "backend_entry"},
            {
                "kind": "route",
                "path": "app/main.py",
                "name": "GET /health/ready",
                "qualified_name": "app.main.create_app.health_ready.__route__.app.get:/health/ready",
                "summary_zh": "健康检查就绪路由",
                "start_line": 279,
                "end_line": 279,
            },
            {
                "kind": "function",
                "path": "app/main.py",
                "qualified_name": "app.main.create_app.health_ready",
                "summary_zh": "健康检查就绪处理函数",
                "start_line": 280,
                "end_line": 283,
            },
            {
                "kind": "route",
                "path": "app/main.py",
                "name": "GET /health",
                "qualified_name": "app.main.create_app.health.__route__.app.get:/health",
                "summary_zh": "健康检查路由",
                "start_line": 275,
                "end_line": 275,
            },
            {
                "kind": "function",
                "path": "app/main.py",
                "qualified_name": "app.main.create_app.health",
                "summary_zh": "健康检查处理函数",
                "start_line": 275,
                "end_line": 276,
            },
        ],
        graph_edges=[
            {
                "kind": "routes_to",
                "from": "route:python:app/main.py:app.main.create_app.health_ready.__route__.app.get:/health/ready",
                "to": "function:python:app/main.py:app.main.create_app.health_ready",
                "path": "app/main.py",
                "line": 279,
            },
            {
                "kind": "routes_to",
                "from": "route:python:app/main.py:app.main.create_app.health.__route__.app.get:/health",
                "to": "function:python:app/main.py:app.main.create_app.health",
                "path": "app/main.py",
                "line": 275,
            },
        ],
        summaries=[],
    )

    evidence_pack = orchestrator._convert_graph_evidence(graph_pack)

    assert evidence_pack.call_chains[0].title == "GET /health -> app.main.create_app.health"


def test_orchestrator_converts_calls_edges_into_call_chain_evidence():
    from app.services.chat.orchestrator import TaskChatOrchestrator
    from app.services.code_graph.evidence_builder import EvidencePack as GraphEvidencePack
    from app.services.code_graph.models import RetrievalCandidate

    orchestrator = TaskChatOrchestrator(
        planning_agent=None,
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=None,
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
    )

    graph_pack = GraphEvidencePack(
        question="用户提交分析任务后，后端主要会经过哪些步骤？",
        normalized_question="说明用户提交分析任务后的后端执行步骤",
        retrieval_objective="定位任务提交入口及下游调用链",
        seeds=[
            RetrievalCandidate(
                task_id="task-hybrid",
                item_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                qualified_name="app.main.create_app.enqueue_turn_task",
                score=120.0,
                source="exact",
                summary_zh="任务提交入口",
            )
        ],
        graph_nodes=[
            {"kind": "file", "path": "app/main.py", "summary_zh": "应用入口文件", "entry_role": "backend_entry"},
            {
                "kind": "function",
                "path": "app/main.py",
                "qualified_name": "app.main.create_app.enqueue_turn_task",
                "summary_zh": "任务提交入口",
                "start_line": 449,
                "end_line": 470,
            },
            {
                "kind": "method",
                "path": "app/task_queue.py",
                "qualified_name": "app.task_queue.InMemoryTaskQueue.submit",
                "summary_zh": "任务入队方法",
                "start_line": 48,
                "end_line": 80,
            },
        ],
        graph_edges=[
            {
                "kind": "calls",
                "from": "function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                "to": "method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                "path": "app/main.py",
                "line": 459,
            }
        ],
        summaries=[],
    )

    evidence_pack = orchestrator._convert_graph_evidence(graph_pack)

    assert any(
        item.title == "app.main.create_app.enqueue_turn_task -> app.task_queue.InMemoryTaskQueue.submit"
        for item in evidence_pack.call_chains
    )
    assert any(
        "调用" in item and "app.task_queue.InMemoryTaskQueue.submit" in item
        for item in evidence_pack.key_findings
    )


def test_orchestrator_prioritizes_primary_calls_over_side_branches():
    from app.services.chat.orchestrator import TaskChatOrchestrator
    from app.services.code_graph.evidence_builder import EvidencePack as GraphEvidencePack
    from app.services.code_graph.models import RetrievalCandidate

    orchestrator = TaskChatOrchestrator(
        planning_agent=None,
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=None,
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
    )

    graph_pack = GraphEvidencePack(
        question="用户提交分析任务后，后端主要会经过哪些核心步骤？",
        normalized_question="说明用户提交分析任务后的后端执行步骤",
        retrieval_objective="定位任务提交入口及下游调用链",
        seeds=[
            RetrievalCandidate(
                task_id="task-hybrid",
                item_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                item_type="symbol",
                path="app/main.py",
                symbol_id="function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                qualified_name="app.main.create_app.enqueue_turn_task",
                score=120.0,
                source="exact",
                summary_zh="任务提交入口",
            ),
            RetrievalCandidate(
                task_id="task-hybrid",
                item_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                item_type="symbol",
                path="app/task_queue.py",
                symbol_id="method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                qualified_name="app.task_queue.InMemoryTaskQueue.submit",
                score=118.0,
                source="exact",
                summary_zh="任务入队方法",
            ),
        ],
        graph_nodes=[
            {"kind": "file", "path": "app/main.py", "summary_zh": "应用入口文件", "entry_role": "backend_entry"},
            {
                "kind": "function",
                "path": "app/main.py",
                "qualified_name": "app.main.create_app.enqueue_turn_task",
                "summary_zh": "任务提交入口",
                "start_line": 449,
                "end_line": 470,
            },
            {
                "kind": "method",
                "path": "app/task_queue.py",
                "qualified_name": "app.task_queue.InMemoryTaskQueue.submit",
                "summary_zh": "任务入队方法",
                "start_line": 56,
                "end_line": 90,
            },
            {
                "kind": "method",
                "path": "app/task_queue.py",
                "qualified_name": "app.task_queue.InMemoryTaskQueue.requeue",
                "summary_zh": "任务重试",
                "start_line": 120,
                "end_line": 145,
            },
        ],
        graph_edges=[
            {
                "kind": "calls",
                "from": "function:python:app/main.py:app.main.create_app.enqueue_turn_task",
                "to": "method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                "path": "app/main.py",
                "line": 459,
            },
            {
                "kind": "calls",
                "from": "method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.requeue",
                "to": "method:python:app/task_queue.py:app.task_queue.InMemoryTaskQueue.submit",
                "path": "app/task_queue.py",
                "line": 137,
            },
        ],
        summaries=[],
    )

    evidence_pack = orchestrator._convert_graph_evidence(graph_pack)

    assert evidence_pack.call_chains[0].title == "app.main.create_app.enqueue_turn_task -> app.task_queue.InMemoryTaskQueue.submit"
    assert all(
        item.title != "app.task_queue.InMemoryTaskQueue.requeue -> app.task_queue.InMemoryTaskQueue.submit"
        for item in evidence_pack.call_chains
    )


@pytest.mark.asyncio
async def test_orchestrator_exposes_hybrid_planner_metadata_fields():
    from app.services.chat.orchestrator import TaskChatOrchestrator

    class _MetadataQuestionAnalyzer:
        async def analyze(self, *, question, history):
            del question, history
            return QuestionAnalysis(
                normalized_question="create_app \u521d\u59cb\u5316\u65f6 app.state \u6302\u8f7d\u4e86\u54ea\u4e9b\u5bf9\u8c61",
                question_type="init_state_explanation",
                answer_depth="detailed",
                retrieval_objective="\u5b9a\u4f4d create_app \u4e2d app.state \u7684\u6302\u8f7d\u9879",
                target_entities=["create_app", "app.state"],
                preferred_item_types=["symbol", "file"],
                search_queries=["create_app", "app.state"],
                raw_keywords=["app.state", "create_app"],
                must_include_entities=["create_app"],
                preferred_evidence_kinds=["state_assignment_fact", "symbol"],
            )

    orchestrator = TaskChatOrchestrator(
        planning_agent=_DonePlanner(),
        fallback_planner=None,
        mcp_gateway=None,
        evidence_assembler=_StubAssembler(),
        answer_composer=_StubComposer(),
        answer_validator=_PassValidator(),
        question_analyzer=_MetadataQuestionAnalyzer(),
        exact_retriever=_HybridExactRetriever(),
        semantic_retriever=None,
        hybrid_ranker=_HybridRanker(),
        graph_expander=_HybridGraphExpander(),
        code_locator=_HybridCodeLocator(),
        graph_evidence_builder=_HybridEvidenceBuilder(),
    )

    response = await orchestrator.answer_question(
        task_id="task-hybrid-meta",
        db_path="tmp.db",
        repo_map_path=None,
        question="create_app \u521d\u59cb\u5316\u65f6\u6302\u8f7d\u4e86\u54ea\u4e9b\u6838\u5fc3\u5bf9\u8c61\u5230 app.state\uff1f",
        history=[],
    )

    assert response.planner_metadata is not None
    assert response.planner_metadata.planning_source == "hybrid_rag"
    assert response.planner_metadata.question_type == "init_state_explanation"
    assert response.planner_metadata.retrieval_objective == "\u5b9a\u4f4d create_app \u4e2d app.state \u7684\u6302\u8f7d\u9879"
    assert response.planner_metadata.search_queries == ["create_app", "app.state"]
    assert response.planner_metadata.must_include_entities == ["create_app"]
    assert response.planner_metadata.preferred_evidence_kinds == ["state_assignment_fact", "symbol"]
