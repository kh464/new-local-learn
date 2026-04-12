import pytest

from app.services.chat.question_analyzer import QuestionAnalyzer


class _FakePlannerLLM:
    async def complete_json(self, *, system_prompt: str, user_prompt: str):
        del system_prompt, user_prompt
        return {
            "normalized_question": "\u8bf4\u660e\u540e\u7aef\u5904\u7406\u903b\u8f91",
            "question_type": "architecture_explanation",
            "answer_depth": "detailed",
            "retrieval_objective": "\u5b9a\u4f4d\u540e\u7aef\u4efb\u52a1\u5904\u7406\u4e3b\u94fe\u8def",
            "target_entities": [],
            "preferred_item_types": ["symbol", "file"],
            "search_queries": ["\u540e\u7aef\u5904\u7406", "\u4e3b\u6d41\u7a0b"],
        }


class _FakeMisclassifiedPlannerLLM:
    async def complete_json(self, *, system_prompt: str, user_prompt: str):
        del system_prompt, user_prompt
        return {
            "normalized_question": "\u9879\u76ee\u4e2d\u7528\u6237\u63d0\u4ea4\u5206\u6790\u4efb\u52a1\u540e\u7684\u540e\u7aef\u5904\u7406\u6d41\u7a0b\u662f\u4ec0\u4e48\uff1f\u8bf7\u6309\u6267\u884c\u987a\u5e8f\u8bf4\u660e",
            "question_type": "call_chain_trace",
            "answer_depth": "detailed",
            "retrieval_objective": "\u5b9a\u4f4d\u4efb\u52a1\u63d0\u4ea4\u6d41\u7a0b",
            "target_entities": [],
            "preferred_item_types": ["symbol", "file", "call_chain"],
            "search_queries": ["\u540e\u7aef\u5904\u7406\u6d41\u7a0b"],
        }


class _FakeUnknownPlannerLLM:
    async def complete_json(self, *, system_prompt: str, user_prompt: str):
        del system_prompt, user_prompt
        return {
            "normalized_question": "\u786e\u8ba4\u4ed3\u5e93\u662f\u5426\u5b58\u5728 health \u68c0\u67e5\u63a5\u53e3",
            "question_type": "unknown",
            "answer_depth": "detailed",
            "retrieval_objective": "\u5b9a\u4f4d health \u63a5\u53e3\u76f8\u5173\u5b9e\u73b0",
            "target_entities": [],
            "preferred_item_types": ["symbol"],
            "search_queries": ["health"],
        }


@pytest.mark.asyncio
async def test_question_analyzer_fallback_extracts_entities_and_types():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="\u8bf7\u8be6\u7ec6\u89e3\u91ca app.main.health \u7684\u8c03\u7528\u94fe",
        history=[],
    )

    assert result.question_type == "call_chain_trace"
    assert result.answer_depth == "code_walkthrough"
    assert "app.main.health" in result.target_entities
    assert result.preferred_item_types == ["symbol", "file", "call_chain"]
    assert "app.main.health" in result.search_queries


@pytest.mark.asyncio
async def test_question_analyzer_fallback_generates_stable_chinese_search_queries():
    analyzer = QuestionAnalyzer()

    result_a = await analyzer.analyze(
        question="\u4ed3\u5e93\u9879\u76ee\u7684\u77e5\u8bc6\u5e93\u662f\u6784\u5efa\u7684\u5417\uff1f",
        history=[],
    )
    result_b = await analyzer.analyze(
        question="\u4ed3\u5e93\u662f\u5426\u5177\u6709\u77e5\u8bc6\u5e93\uff1f",
        history=[],
    )

    assert "\u77e5\u8bc6\u5e93" in result_a.search_queries
    assert "\u77e5\u8bc6\u5e93" in result_b.search_queries


@pytest.mark.asyncio
async def test_question_analyzer_preserves_structured_route_search_queries():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="GET /health \u662f\u7531\u54ea\u4e2a\u51fd\u6570\u5904\u7406\u7684\uff1f\u8bf7\u7ed9\u51fa\u6587\u4ef6\u4f4d\u7f6e\u3002",
        history=[],
    )

    assert result.question_type == "call_chain_trace"
    assert "GET /health" in result.search_queries
    assert "/health" in result.search_queries


@pytest.mark.asyncio
async def test_question_analyzer_adds_task_flow_anchors_for_analysis_pipeline_questions():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="\u5f53\u524d\u9879\u76ee\u4e2d\uff0c\u7528\u6237\u63d0\u4ea4\u4e00\u6b21\u5206\u6790\u4efb\u52a1\u540e\uff0c\u540e\u7aef\u4e3b\u8981\u4f1a\u7ecf\u8fc7\u54ea\u4e9b\u6838\u5fc3\u6b65\u9aa4\uff1f\u8bf7\u6309\u6267\u884c\u987a\u5e8f\u8bf4\u660e\u3002",
        history=[],
    )

    assert result.question_type == "architecture_explanation"
    assert "task_queue.py" in result.search_queries
    assert "task_queue" in result.search_queries
    assert "enqueue" in result.search_queries
    assert "submit" in result.search_queries
    assert "_worker_loop" in result.search_queries
    assert "run_analysis_job" not in result.search_queries
    assert "/analyze" not in result.search_queries


@pytest.mark.asyncio
async def test_question_analyzer_treats_process_questions_as_architecture_not_call_chain():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="\u5f53\u524d\u9879\u76ee\u4e2d\uff0c\u7528\u6237\u63d0\u4ea4\u4e00\u6b21\u5206\u6790\u4efb\u52a1\u540e\uff0c\u540e\u7aef\u5904\u7406\u6d41\u7a0b\u662f\u4ec0\u4e48\uff1f\u8bf7\u6309\u6267\u884c\u987a\u5e8f\u8bf4\u660e\u3002",
        history=[],
    )

    assert result.question_type == "architecture_explanation"
    assert "task_queue.py" in result.search_queries


@pytest.mark.asyncio
async def test_question_analyzer_llm_path_still_preserves_task_flow_anchors_from_original_question():
    analyzer = QuestionAnalyzer(llm_client=_FakePlannerLLM())

    result = await analyzer.analyze(
        question="\u5f53\u524d\u9879\u76ee\u4e2d\uff0c\u7528\u6237\u63d0\u4ea4\u4e00\u6b21\u5206\u6790\u4efb\u52a1\u540e\uff0c\u540e\u7aef\u4e3b\u8981\u4f1a\u7ecf\u8fc7\u54ea\u4e9b\u6838\u5fc3\u6b65\u9aa4\uff1f\u8bf7\u6309\u6267\u884c\u987a\u5e8f\u8bf4\u660e\u3002",
        history=[],
    )

    assert result.question_type == "architecture_explanation"
    assert "task_queue.py" in result.search_queries
    assert "submit" in result.search_queries
    assert "enqueue" in result.search_queries
    assert "_worker_loop" in result.search_queries
    assert "run_analysis_job" not in result.search_queries


@pytest.mark.asyncio
async def test_question_analyzer_llm_path_corrects_task_flow_misclassification():
    analyzer = QuestionAnalyzer(llm_client=_FakeMisclassifiedPlannerLLM())

    result = await analyzer.analyze(
        question="\u5f53\u524d\u9879\u76ee\u4e2d\uff0c\u7528\u6237\u63d0\u4ea4\u4e00\u6b21\u5206\u6790\u4efb\u52a1\u540e\uff0c\u540e\u7aef\u5904\u7406\u6d41\u7a0b\u662f\u4ec0\u4e48\uff1f\u8bf7\u6309\u6267\u884c\u987a\u5e8f\u8bf4\u660e\u3002",
        history=[],
    )

    assert result.question_type == "architecture_explanation"
    assert "task_queue.py" in result.search_queries


@pytest.mark.asyncio
async def test_question_analyzer_classifies_app_state_question_as_init_state_explanation():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="create_app \u521d\u59cb\u5316\u65f6\u6302\u8f7d\u4e86\u54ea\u4e9b\u6838\u5fc3\u5bf9\u8c61\u5230 app.state\uff1f",
        history=[],
    )

    assert result.question_type == "init_state_explanation"
    assert "app.state" in result.raw_keywords
    assert "create_app" in result.search_queries
    assert "app.state" in result.search_queries
    assert "state_assignment_fact" in result.preferred_evidence_kinds
    assert "create_app" in result.must_include_entities


@pytest.mark.asyncio
async def test_question_analyzer_classifies_queue_backend_question_as_capability_check():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="\u5f53\u524d\u9879\u76ee\u652f\u6301\u54ea\u51e0\u79cd\u4efb\u52a1\u961f\u5217\u540e\u7aef\uff1f",
        history=[],
    )

    assert result.question_type == "capability_check"
    assert "\u4efb\u52a1\u961f\u5217" in result.raw_keywords
    assert "\u540e\u7aef" in result.raw_keywords
    assert "capability_fact" in result.preferred_evidence_kinds
    assert any(query in result.search_queries for query in ["\u4efb\u52a1\u961f\u5217", "queue backend", "task queue"])


@pytest.mark.asyncio
async def test_question_analyzer_classifies_realtime_status_question_as_frontend_backend_flow():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="\u524d\u7aef\u5982\u4f55\u5b9e\u65f6\u83b7\u53d6\u4efb\u52a1\u72b6\u6001\u66f4\u65b0\uff1f",
        history=[],
    )

    assert result.question_type == "frontend_backend_flow"
    assert "\u524d\u7aef" in result.raw_keywords
    assert any(keyword in result.raw_keywords for keyword in ["\u5b9e\u65f6", "\u4efb\u52a1\u72b6\u6001", "websocket"])
    assert "frontend_api_fact" in result.preferred_evidence_kinds
    assert "route_fact" in result.preferred_evidence_kinds


@pytest.mark.asyncio
async def test_question_analyzer_classifies_health_inventory_question_as_api_inventory():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="\u5f53\u524d\u9879\u76ee\u7684\u5065\u5eb7\u68c0\u67e5\u63a5\u53e3\u6709\u54ea\u4e9b\uff1f",
        history=[],
    )

    assert result.question_type == "api_inventory"
    assert "\u5065\u5eb7\u68c0\u67e5" in result.raw_keywords
    assert "health_fact" in result.preferred_evidence_kinds
    assert any(query in result.search_queries for query in ["\u5065\u5eb7\u68c0\u67e5", "/health", "health"])


@pytest.mark.asyncio
async def test_question_analyzer_llm_unknown_falls_back_to_rule_classification():
    analyzer = QuestionAnalyzer(llm_client=_FakeUnknownPlannerLLM())

    result = await analyzer.analyze(
        question="\u5f53\u524d\u9879\u76ee\u7684 health \u68c0\u67e5\u63a5\u53e3\u6709\u54ea\u4e9b\uff1f",
        history=[],
    )

    assert result.question_type == "api_inventory"
    assert "/health" in result.search_queries or "health" in result.search_queries
    assert "health_fact" in result.preferred_evidence_kinds


@pytest.mark.asyncio
async def test_question_analyzer_uses_planning_context_hints_to_stabilize_knowledge_queries():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="这个仓库是否具有知识库能力？",
        history=[],
        planning_context={
            "file_hints": [
                {
                    "path": "app/services/knowledge/retriever.py",
                    "summary_zh": "负责仓库知识库检索与证据组装。",
                    "entry_role": None,
                }
            ],
            "symbol_hints": [
                {
                    "qualified_name": "app.services.knowledge.retriever.KnowledgeRetriever",
                    "file_path": "app/services/knowledge/retriever.py",
                    "summary_zh": "知识库检索器，负责聚合代码证据。",
                    "symbol_kind": "class",
                }
            ],
        },
    )

    assert "app/services/knowledge/retriever.py" in result.search_queries
    assert "app.services.knowledge.retriever.KnowledgeRetriever" in result.search_queries


@pytest.mark.asyncio
async def test_question_analyzer_uses_relation_hints_to_anchor_architecture_queries():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="用户提交分析任务后主链路是什么？",
        history=[],
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
    assert "任务队列" in result.search_queries
