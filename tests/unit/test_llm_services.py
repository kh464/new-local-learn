from __future__ import annotations

import json

import httpx
import pytest


def test_load_runtime_config_reads_default_profile(tmp_path):
    config_path = tmp_path / "llm.yaml"
    config_path.write_text(
        """
version: 1
llm:
  default_provider: demo
  default_profile: chat
  timeout_seconds: 45
  max_retries: 3
  providers:
    demo:
      enabled: true
      base_url: https://example.test/v1
      api_key: secret-token
      generation:
        temperature: 0.2
        top_p: 0.8
        max_tokens: 700
  routing:
    profiles:
      chat:
        provider: demo
        model: demo-model
""".strip(),
        encoding="utf-8",
    )

    from app.services.llm.config import load_runtime_config

    runtime_config = load_runtime_config(config_path)

    assert runtime_config.timeout_seconds == 45
    assert runtime_config.max_retries == 3
    assert runtime_config.profile.model == "demo-model"
    assert runtime_config.provider.base_url == "https://example.test/v1"
    assert runtime_config.provider.api_key.get_secret_value() == "secret-token"
    assert runtime_config.provider.generation.max_tokens == 700


def test_tutor_composer_returns_chinese_guidance():
    from app.services.analyzers.tutor_composer import TutorComposer

    tutorial = TutorComposer().compose({"frameworks": ["fastapi", "vue"]}, {"flows": [{"backend_route": "/api/v1/analyze"}]})

    assert tutorial["mental_model"] == "把这个项目理解为由 fastapi, vue 组成的一条处理链路。"
    assert tutorial["run_steps"][0].startswith("先找到")
    assert tutorial["pitfalls"][0].startswith("不要想当然")
    assert tutorial["self_check_questions"][0].startswith("入口")


@pytest.mark.asyncio
async def test_chat_completion_client_uses_profile_configuration():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"mental_model":"LLM mental model","run_steps":["step 1"],'
                                '"pitfalls":["pitfall 1"],"self_check_questions":["question 1"]}'
                            )
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)

    from app.services.llm.client import ChatCompletionClient
    from app.services.llm.config import GenerationConfig, ProviderConfig, RuntimeConfig, RoutingProfile

    client = ChatCompletionClient(
        RuntimeConfig(
            timeout_seconds=30,
            max_retries=2,
            profile=RoutingProfile(provider="demo", model="demo-model"),
            provider=ProviderConfig(
                name="demo",
                base_url="https://example.test/v1",
                api_key="secret-token",
                generation=GenerationConfig(temperature=0.4, top_p=0.9, max_tokens=600),
            ),
        ),
        transport=transport,
    )

    response = await client.complete_json(
        system_prompt="system prompt",
        user_prompt="user prompt",
    )

    assert response["mental_model"] == "LLM mental model"
    assert len(requests) == 1
    assert requests[0].url == httpx.URL("https://example.test/v1/chat/completions")
    assert requests[0].headers["Authorization"] == "Bearer secret-token"
    payload = json.loads(requests[0].content.decode("utf-8"))
    assert payload["model"] == "demo-model"
    assert payload["temperature"] == 0.4
    assert payload["max_tokens"] == 600


@pytest.mark.asyncio
async def test_tutorial_llm_enhancer_requires_chinese_output():
    captured: dict[str, str] = {}

    class StubClient:
        async def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return {
                "mental_model": "LLM mental model",
                "run_steps": ["step 1", "step 2", "step 3"],
                "pitfalls": ["pitfall 1", "pitfall 2"],
                "self_check_questions": ["question 1", "question 2", "question 3"],
            }

    from app.services.llm.report_enhancer import TutorialLLMEnhancer

    enhancer = TutorialLLMEnhancer(StubClient())

    with pytest.raises(ValueError, match="Chinese"):
        await enhancer.generate_tutorial(
            repo_summary={"name": "demo", "key_files": ["app/main.py"], "file_count": 1},
            detected_stack={"frameworks": ["fastapi"], "languages": ["python"]},
            backend_summary={"routes": []},
            frontend_summary={"framework": "vue", "routing": [], "api_calls": [], "state_units": [], "components": []},
            logic_summary={"flows": []},
            file_contents={"app/main.py": "from fastapi import FastAPI"},
        )

    assert "简体中文" in captured["system_prompt"]
    assert "所有字段的值都必须使用简体中文" in captured["system_prompt"]
    assert "必须输出中文" in captured["user_prompt"]
