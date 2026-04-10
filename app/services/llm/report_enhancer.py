from __future__ import annotations

import json
import re

from app.core.models import TutorialSummary
from app.services.llm.client import ChatCompletionClient

_SYSTEM_PROMPT = """你是一名面向初学者的仓库学习导师。
你必须返回严格的 JSON，并且只能包含以下键：
- mental_model: string
- run_steps: array of 3 to 6 strings
- pitfalls: array of 2 to 5 strings
- self_check_questions: array of 3 to 5 strings
硬性要求：
1. 所有字段的值都必须使用简体中文。
2. 即使仓库中的文件名、框架名或代码片段包含英文，解释句子也必须使用中文。
3. 禁止输出英文句子，禁止输出拼音，禁止输出 Markdown 代码块。
4. 内容必须结合仓库细节，不能写空话。"""

_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class TutorialLLMEnhancer:
    def __init__(
        self,
        client: ChatCompletionClient,
        *,
        max_prompt_chars: int = 20000,
        max_snippet_chars: int = 1200,
    ) -> None:
        self._client = client
        self._max_prompt_chars = max_prompt_chars
        self._max_snippet_chars = max_snippet_chars

    async def generate_tutorial(
        self,
        *,
        repo_summary: dict[str, object],
        detected_stack: dict[str, object],
        backend_summary: dict[str, object],
        frontend_summary: dict[str, object],
        logic_summary: dict[str, object],
        file_contents: dict[str, str],
    ) -> dict[str, object]:
        prompt_payload = {
            "repo_summary": {
                "name": repo_summary.get("name"),
                "key_files": repo_summary.get("key_files", []),
                "file_count": repo_summary.get("file_count"),
            },
            "detected_stack": detected_stack,
            "backend_summary": backend_summary,
            "frontend_summary": frontend_summary,
            "logic_summary": logic_summary,
            "file_snippets": self._build_file_snippets(repo_summary, file_contents),
        }
        user_prompt = json.dumps(prompt_payload, ensure_ascii=False)
        if len(user_prompt) > self._max_prompt_chars:
            user_prompt = user_prompt[: self._max_prompt_chars]
        user_prompt = (
            "必须输出中文。所有解释、步骤、陷阱和自检问题都必须使用简体中文，"
            "不能输出英文句子。\n"
            f"{user_prompt}"
        )

        response = await self._client.complete_json(system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt)
        tutorial = TutorialSummary.model_validate(response)
        self._ensure_chinese_output(tutorial)
        return tutorial.model_dump()

    def _build_file_snippets(
        self,
        repo_summary: dict[str, object],
        file_contents: dict[str, str],
    ) -> dict[str, str]:
        snippets: dict[str, str] = {}
        key_files = repo_summary.get("key_files", [])
        selected_files: list[str] = []
        if isinstance(key_files, list):
            selected_files.extend(path for path in key_files if isinstance(path, str))
        for path in file_contents:
            if path not in selected_files:
                selected_files.append(path)
            if len(selected_files) >= 6:
                break

        for path in selected_files[:6]:
            content = file_contents.get(path)
            if isinstance(content, str) and content:
                snippets[path] = content[: self._max_snippet_chars]
        return snippets

    def _ensure_chinese_output(self, tutorial: TutorialSummary) -> None:
        text_fields = [tutorial.mental_model, *tutorial.run_steps, *tutorial.pitfalls, *tutorial.self_check_questions]
        if not text_fields or any(not _CJK_PATTERN.search(text) for text in text_fields if text.strip()):
            raise ValueError("LLM tutorial output must be Chinese.")
