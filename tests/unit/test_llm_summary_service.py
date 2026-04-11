from __future__ import annotations

import pytest

from app.services.code_graph.llm_summary_service import LlmSummaryService


@pytest.mark.asyncio
async def test_llm_summary_service_generates_file_summary_payload():
    captured: dict[str, str] = {}

    class StubClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return {
                "summary_zh": "该文件负责创建 FastAPI 应用并提供健康检查入口。",
                "responsibility_zh": "负责应用入口初始化与基础路由挂载",
                "upstream_zh": "由 Uvicorn 启动时导入",
                "downstream_zh": "向 health 处理函数分发请求",
                "keywords_zh": ["FastAPI", "入口", "health"],
                "summary_confidence": "high",
            }

    service = LlmSummaryService(client=StubClient())
    payload = await service.generate_file_summary(
        file_path="app/main.py",
        language="python",
        evidence={
            "symbol_facts": ["定义了 health 函数", "定义了 FastAPI app"],
            "code_snippets": ["app = FastAPI()", "@app.get('/health')"],
        },
    )

    assert payload.summary_zh.startswith("该文件负责创建 FastAPI")
    assert payload.keywords_zh == ["FastAPI", "入口", "health"]
    assert payload.summary_confidence == "high"
    assert "只能输出 JSON" in captured["system_prompt"]
    assert "必须使用简体中文" in captured["system_prompt"]
    assert "app/main.py" in captured["user_prompt"]


@pytest.mark.asyncio
async def test_llm_summary_service_generates_symbol_summary_payload():
    captured: dict[str, str] = {}

    class StubClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return {
                "summary_zh": "该函数负责返回健康检查结果。",
                "input_output_zh": "无输入，输出健康状态字典",
                "side_effects_zh": "无外部副作用",
                "call_targets_zh": "无下游调用",
                "callers_zh": "由 FastAPI 路由触发",
                "summary_confidence": "medium",
            }

    service = LlmSummaryService(client=StubClient())
    payload = await service.generate_symbol_summary(
        symbol_name="app.main.health",
        symbol_kind="function",
        file_path="app/main.py",
        language="python",
        evidence={
            "signature": "def health() -> dict[str, str]",
            "call_targets": [],
            "callers": ["FastAPI GET /health"],
        },
    )

    assert payload.summary_zh == "该函数负责返回健康检查结果。"
    assert payload.input_output_zh == "无输入，输出健康状态字典"
    assert payload.summary_confidence == "medium"
    assert "只能输出 JSON" in captured["system_prompt"]
    assert "app.main.health" in captured["user_prompt"]
