import pytest

from app.services.chat.llm_planning_agent import LlmPlanningAgent


class StubClient:
    def __init__(self, response: dict[str, object] | None = None) -> None:
        self.response = response or {
            "inferred_intent": "定位登录能力并逐步讲解",
            "answer_depth": "code_walkthrough",
            "current_hypothesis": "需要先定位登录入口文件",
            "gaps": ["尚未定位登录入口文件"],
            "question_type": "capability_check",
            "normalized_question": "确认项目登录能力的实现位置",
            "retrieval_objective": "定位登录相关入口、处理函数和认证实现",
            "search_queries": ["登录", "login", "auth", "signin"],
            "must_include_entities": ["login", "auth"],
            "preferred_evidence_kinds": ["capability_fact", "symbol"],
            "ready_to_answer": False,
            "tool_call": {
                "name": "search_code",
                "arguments": {"query": "login auth signin 登录"},
                "reason": "先定位登录相关源码文件",
            },
        }
        self.last_system_prompt = ""
        self.last_user_prompt = ""

    async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return self.response


@pytest.mark.asyncio
async def test_llm_planning_agent_returns_tool_call():
    client = StubClient()
    agent = LlmPlanningAgent(client=client)
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
    assert result.question_type == "capability_check"
    assert result.normalized_question == "确认项目登录能力的实现位置"
    assert result.retrieval_objective == "定位登录相关入口、处理函数和认证实现"
    assert result.search_queries == ["登录", "login", "auth", "signin"]
    assert result.must_include_entities == ["login", "auth"]
    assert result.preferred_evidence_kinds == ["capability_fact", "symbol"]
    assert "必须严格输出 JSON" in client.last_system_prompt
    assert "tool_call.name 必须只能使用 available_tools" in client.last_system_prompt
    assert '"available_tools": ["search_code", "open_file"]' in client.last_user_prompt


@pytest.mark.asyncio
async def test_llm_planning_agent_normalizes_missing_retrieval_fields():
    client = StubClient(
        {
            "inferred_intent": "确认仓库是否实现知识库能力",
            "answer_depth": "detailed",
            "current_hypothesis": "需要先定位知识库相关模块",
            "gaps": ["尚未定位知识库实现模块"],
            "ready_to_answer": False,
            "tool_call": {
                "name": "search_code",
                "arguments": {"query": "仓库是否具有知识库"},
                "reason": "先定位知识库能力相关实现",
            },
        }
    )
    agent = LlmPlanningAgent(client=client)

    result = await agent.plan(
        question="仓库是否具有具有知识库",
        history=[],
        observations=[],
        available_tools=["search_code", "open_file"],
        loop_count=0,
        remaining_loops=5,
    )

    assert "normalized_question" in client.last_system_prompt
    assert "retrieval_objective" in client.last_system_prompt
    assert "search_queries" in client.last_system_prompt
    assert result.normalized_question == "仓库是否具有具有知识库"
    assert result.retrieval_objective == "确认仓库是否实现知识库能力"
    assert "知识库" in result.search_queries


@pytest.mark.asyncio
async def test_llm_planning_agent_rejects_unsupported_tool_name():
    agent = LlmPlanningAgent(
        client=StubClient(
            {
                "inferred_intent": "定位登录功能",
                "answer_depth": "detailed",
                "current_hypothesis": "需要先搜索代码",
                "gaps": [],
                "ready_to_answer": False,
                "tool_call": {
                    "name": "unknown_tool",
                    "arguments": {"query": "login"},
                    "reason": "尝试调用不存在的工具",
                },
            }
        )
    )

    with pytest.raises(ValueError, match="available_tools"):
        await agent.plan(
            question="帮我找登录逻辑",
            history=[],
            observations=[],
            available_tools=["search_code", "open_file"],
            loop_count=0,
            remaining_loops=5,
        )


@pytest.mark.asyncio
async def test_llm_planning_agent_rejects_ready_to_answer_with_tool_call():
    agent = LlmPlanningAgent(
        client=StubClient(
            {
                "inferred_intent": "已经可以回答",
                "answer_depth": "overview",
                "current_hypothesis": "信息已经足够",
                "gaps": [],
                "ready_to_answer": True,
                "tool_call": {
                    "name": "search_code",
                    "arguments": {"query": "login"},
                    "reason": "仍然想继续搜索",
                },
            }
        )
    )

    with pytest.raises(ValueError, match="ready_to_answer"):
        await agent.plan(
            question="总结登录实现",
            history=[],
            observations=[],
            available_tools=["search_code", "open_file"],
            loop_count=1,
            remaining_loops=4,
        )


@pytest.mark.asyncio
async def test_llm_planning_agent_rejects_invalid_answer_depth():
    agent = LlmPlanningAgent(
        client=StubClient(
            {
                "inferred_intent": "定位登录功能",
                "answer_depth": "summary",
                "current_hypothesis": "需要先搜索代码",
                "gaps": [],
                "ready_to_answer": False,
                "tool_call": {
                    "name": "search_code",
                    "arguments": {"query": "login"},
                    "reason": "先搜索相关代码",
                },
            }
        )
    )

    with pytest.raises(ValueError, match="answer_depth"):
        await agent.plan(
            question="帮我分析登录逻辑",
            history=[],
            observations=[],
            available_tools=["search_code", "open_file"],
            loop_count=0,
            remaining_loops=5,
        )


@pytest.mark.asyncio
async def test_llm_planning_agent_rejects_non_actionable_result():
    agent = LlmPlanningAgent(
        client=StubClient(
            {
                "inferred_intent": "定位登录功能",
                "answer_depth": "detailed",
                "current_hypothesis": "还需要继续调查",
                "gaps": ["尚未定位入口文件"],
                "ready_to_answer": False,
                "tool_call": None,
            }
        )
    )

    with pytest.raises(ValueError, match="tool_call"):
        await agent.plan(
            question="帮我分析登录逻辑",
            history=[],
            observations=[],
            available_tools=["search_code", "open_file"],
            loop_count=0,
            remaining_loops=5,
        )


@pytest.mark.asyncio
async def test_llm_planning_agent_uses_planning_context_hints_for_prompt_and_query_completion():
    client = StubClient(
        {
            "inferred_intent": "确认仓库是否实现知识库能力",
            "answer_depth": "detailed",
            "current_hypothesis": "需要先定位知识库相关模块",
            "gaps": ["尚未定位知识库实现模块"],
            "normalized_question": "确认仓库是否实现知识库能力及相关实现位置",
            "retrieval_objective": "定位知识库相关入口、检索器与实现文件",
            "search_queries": [],
            "ready_to_answer": False,
            "tool_call": {
                "name": "search_code",
                "arguments": {"query": "knowledge"},
                "reason": "先定位知识库相关实现",
            },
        }
    )
    agent = LlmPlanningAgent(client=client)

    result = await agent.plan(
        question="这个仓库是否具有知识库能力？",
        history=[],
        observations=[],
        available_tools=["search_code", "open_file"],
        loop_count=0,
        remaining_loops=5,
        planning_context={
            "file_hints": [
                {
                    "path": "app/services/knowledge/retriever.py",
                    "summary_zh": "负责仓库知识库检索与证据组装。",
                }
            ],
            "symbol_hints": [
                {
                    "qualified_name": "app.services.knowledge.retriever.KnowledgeRetriever",
                    "file_path": "app/services/knowledge/retriever.py",
                    "summary_zh": "知识库检索器，负责聚合代码证据。",
                }
            ],
        },
    )

    assert '"planning_context"' in client.last_user_prompt
    assert "app/services/knowledge/retriever.py" in result.search_queries
    assert "app.services.knowledge.retriever.KnowledgeRetriever" in result.search_queries


@pytest.mark.asyncio
async def test_llm_planning_agent_uses_relation_hints_for_query_completion():
    client = StubClient(
        {
            "inferred_intent": "说明分析任务提交流程",
            "answer_depth": "detailed",
            "current_hypothesis": "需要先定位主调用链",
            "gaps": ["尚未锁定主链路"],
            "normalized_question": "说明分析任务提交后的主调用链",
            "retrieval_objective": "定位任务提交入口及主调用关系",
            "search_queries": [],
            "ready_to_answer": False,
            "tool_call": {
                "name": "search_code",
                "arguments": {"query": "task_queue"},
                "reason": "先定位任务提交主链路",
            },
        }
    )
    agent = LlmPlanningAgent(client=client)

    result = await agent.plan(
        question="用户提交分析任务后主链路是什么？",
        history=[],
        observations=[],
        available_tools=["search_code", "open_file"],
        loop_count=0,
        remaining_loops=5,
        planning_context={
            "keyword_hints": ["任务队列", "提交任务"],
            "relation_hints": [
                {
                    "edge_kind": "calls",
                    "from_qualified_name": "app.main.create_app.enqueue_turn_task",
                    "to_qualified_name": "app.task_queue.InMemoryTaskQueue.submit",
                    "source_path": "app/main.py",
                }
            ],
        },
    )

    assert "app.main.create_app.enqueue_turn_task" in result.search_queries
    assert "app.task_queue.InMemoryTaskQueue.submit" in result.search_queries


@pytest.mark.asyncio
async def test_llm_planning_agent_normalizes_missing_structured_planning_fields():
    client = StubClient(
        {
            "inferred_intent": "说明 create_app 初始化时挂载了哪些 app.state 对象",
            "answer_depth": "detailed",
            "current_hypothesis": "需要先定位 create_app 和 app.state",
            "gaps": ["尚未定位状态挂载点"],
            "normalized_question": "说明 create_app 初始化时挂载了哪些 app.state 对象",
            "retrieval_objective": "定位 create_app 中 app.state 的挂载项",
            "search_queries": ["create_app", "app.state"],
            "ready_to_answer": False,
            "tool_call": {
                "name": "search_code",
                "arguments": {"query": "create_app app.state"},
                "reason": "先定位状态挂载点",
            },
        }
    )
    agent = LlmPlanningAgent(client=client)

    result = await agent.plan(
        question="create_app 初始化时挂载了哪些核心对象到 app.state？",
        history=[],
        observations=[],
        available_tools=["search_code", "open_file"],
        loop_count=0,
        remaining_loops=5,
    )

    assert result.question_type == "module_responsibility"
    assert result.must_include_entities == []
    assert result.preferred_evidence_kinds == []
