from __future__ import annotations

import pytest

from app.core.models import AnalysisResult


@pytest.mark.asyncio
async def test_repository_chat_service_uses_llm_and_returns_chinese_answer(sample_analysis_result: AnalysisResult):
    captured: dict[str, str] = {}

    class StubClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return {
                "answer": "后端入口在 app/main.py，这里创建了 FastAPI 应用并注册了健康检查路由。",
                "citations": [
                    {
                        "path": "app/main.py",
                        "start_line": 1,
                        "end_line": 8,
                        "reason": "这里定义了应用实例和路由。",
                        "snippet": "from fastapi import FastAPI",
                    }
                ],
                "supplemental_notes": ["如果你要继续追请求链路，可以再看 web/App.tsx 到 app/main.py 的调用关系。"],
                "confidence": "high",
            }

    from app.services.llm.repo_chat import RepositoryChatService

    service = RepositoryChatService(client=StubClient())
    response = await service.answer_question(
        question="这个仓库的后端入口在哪里？",
        result=sample_analysis_result,
        history=[],
    )

    assert "后端入口" in response.answer
    assert response.citations[0].path == "app/main.py"
    assert "必须使用简体中文" in captured["system_prompt"]
    assert "这个仓库的后端入口在哪里" in captured["user_prompt"]


@pytest.mark.asyncio
async def test_repository_chat_service_falls_back_to_deterministic_answer_when_llm_fails(
    sample_analysis_result: AnalysisResult,
):
    class BrokenClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            raise RuntimeError("llm unavailable")

    from app.services.llm.repo_chat import RepositoryChatService

    service = RepositoryChatService(client=BrokenClient())
    response = await service.answer_question(
        question="前端通过哪个文件调用后端接口？",
        result=sample_analysis_result,
        history=[],
    )

    assert "当前仓库" in response.answer
    assert response.citations
    assert response.citations[0].path in {"web/App.tsx", "app/main.py"}
