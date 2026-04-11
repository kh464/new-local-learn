import pytest

from app.services.chat.question_analyzer import QuestionAnalyzer


@pytest.mark.asyncio
async def test_question_analyzer_fallback_extracts_entities_and_types():
    analyzer = QuestionAnalyzer()

    result = await analyzer.analyze(
        question="请详细解释 app.main.health 的调用链",
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
        question="仓库项目的知识库是构建的吗？",
        history=[],
    )
    result_b = await analyzer.analyze(
        question="仓库是否具有知识库？",
        history=[],
    )

    assert "知识库" in result_a.search_queries
    assert "知识库" in result_b.search_queries
