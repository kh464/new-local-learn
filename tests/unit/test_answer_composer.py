import pytest

from app.services.chat.answer_composer import AnswerComposer
from app.services.chat.models import EvidenceItem, EvidencePack


def _build_evidence_pack() -> EvidencePack:
    return EvidencePack(
        question="前端请求如何到后端？",
        planning_source="llm",
        question_type="frontend_backend_flow",
        retrieval_objective="定位前端请求入口与后端处理链路",
        must_include_entities=["GET /health", "app/main.py"],
        preferred_evidence_kinds=["call_chain", "route_fact"],
        call_chains=[
            EvidenceItem(
                kind="call_chain",
                title="web/src/App.tsx -> GET /health -> app/main.py:health",
                summary="web/src/App.tsx -> GET /health -> app/main.py:health",
                path="app/main.py",
            )
        ],
        citations=[
            EvidenceItem(
                kind="citation",
                title="health route",
                summary="FastAPI health route",
                path="app/main.py",
                start_line=1,
                end_line=8,
                snippet="@app.get('/health')",
            )
        ],
        key_findings=["已确认调用链：web/src/App.tsx -> GET /health -> app/main.py:health"],
        confidence_basis=["命中调用链和真实代码片段"],
    )


@pytest.mark.asyncio
async def test_answer_composer_uses_llm_when_client_available():
    captured: dict[str, str] = {}

    class StubClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return {
                "answer": "根据已收集的调用链证据，前端在 web/src/App.tsx 发起请求，后端入口在 app/main.py:health。",
                "supplemental_notes": ["这是基于真实代码证据生成的回答。"],
                "confidence": "high",
            }

    composer = AnswerComposer(client=StubClient())

    result = await composer.compose(
        question="前端请求如何到后端？",
        evidence_pack=_build_evidence_pack(),
        history=[],
    )

    assert result["answer_source"] == "llm"
    assert "前端在 web/src/App.tsx 发起请求" in result["answer"]
    assert "只能基于证据回答" in captured["system_prompt"]
    assert "先直接回答用户问题" in captured["system_prompt"]
    assert "区分“已确认事实”和“推断”" in captured["system_prompt"]
    assert "app/main.py" in captured["user_prompt"]
    assert "confirmed_facts" in captured["user_prompt"]
    assert "inferences" in captured["user_prompt"]
    assert "evidence_gaps" in captured["user_prompt"]
    assert "answer_focus" in captured["user_prompt"]
    assert "must_include_entities" in captured["user_prompt"]


@pytest.mark.asyncio
async def test_answer_composer_falls_back_to_local_when_llm_fails():
    class BrokenClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            raise RuntimeError("provider timeout")

    composer = AnswerComposer(client=BrokenClient())

    result = await composer.compose(
        question="前端请求如何到后端？",
        evidence_pack=_build_evidence_pack(),
        history=[],
    )

    assert result["answer_source"] == "local"
    assert "web/src/App.tsx -> GET /health -> app/main.py:health" in result["answer"]


@pytest.mark.asyncio
async def test_answer_composer_local_fallback_reports_missing_evidence():
    composer = AnswerComposer()

    result = await composer.compose(
        question="这个仓库是否具有知识库？",
        evidence_pack=EvidencePack(
            question="这个仓库是否具有知识库？",
            planning_source="hybrid_rag",
            files=[],
            symbols=[],
            citations=[],
            key_findings=[],
            gaps=["尚未定位到知识库入口文件", "尚未命中相关代码片段"],
        ),
        history=[],
    )

    assert result["answer_source"] == "local"
    assert "证据不足" in result["answer"]
    assert "知识库" in result["answer"]
    assert any("尚未定位到知识库入口文件" in note for note in result["supplemental_notes"])


@pytest.mark.asyncio
async def test_answer_composer_local_fallback_uses_route_evidence_when_available():
    composer = AnswerComposer()

    result = await composer.compose(
        question="GET /health 是由哪个函数处理的？请给出文件位置。",
        evidence_pack=EvidencePack(
            question="GET /health 是由哪个函数处理的？请给出文件位置。",
            planning_source="hybrid_rag",
            routes=[
                EvidenceItem(
                    kind="route",
                    path="app/main.py",
                    title="GET /health",
                    summary="该路由定义在 app/main.py:274，并指向处理函数 app.main.create_app.health。",
                    start_line=274,
                    end_line=274,
                )
            ],
            citations=[
                EvidenceItem(
                    kind="citation",
                    path="app/main.py",
                    title="app.main.create_app.health",
                    summary="app.main.create_app.health",
                    start_line=275,
                    end_line=278,
                    snippet="    @app.get('/health')\n    async def health():\n        return {'status': 'ok'}",
                )
            ],
            key_findings=["已确认 GET /health 在 app/main.py:274 定义，并由 app.main.create_app.health 处理。"],
        ),
        history=[],
    )

    assert result["answer_source"] == "local"
    assert "GET /health" in result["answer"]
    assert "app/main.py" in result["answer"]
    assert "app.main.create_app.health" in "".join(result["supplemental_notes"])


@pytest.mark.asyncio
async def test_answer_composer_local_fallback_prioritizes_must_include_call_chain():
    composer = AnswerComposer()

    result = await composer.compose(
        question="说明任务提交后的主链路",
        evidence_pack=EvidencePack(
            question="说明任务提交后的主链路",
            planning_source="hybrid_rag",
            question_type="architecture_explanation",
            retrieval_objective="定位任务提交入口及下游主调用链",
            must_include_entities=["enqueue_turn_task"],
            preferred_evidence_kinds=["call_chain", "symbol"],
            call_chains=[
                EvidenceItem(
                    kind="call_chain",
                    path="app/a_side.py",
                    title="app.a_side.requeue -> app.task_queue.InMemoryTaskQueue.submit",
                    summary="旁支重试逻辑调用任务入队。",
                ),
                EvidenceItem(
                    kind="call_chain",
                    path="app/main.py",
                    title="app.main.create_app.enqueue_turn_task -> app.task_queue.InMemoryTaskQueue.submit",
                    summary="主任务提交入口调用任务入队。",
                ),
            ],
            key_findings=["已确认主链路涉及 enqueue_turn_task。"],
        ),
        history=[],
    )

    assert result["answer_source"] == "local"
    assert "app.main.create_app.enqueue_turn_task -> app.task_queue.InMemoryTaskQueue.submit" in result["answer"]
