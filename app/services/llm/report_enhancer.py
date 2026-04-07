from __future__ import annotations

import json

from app.core.models import TutorialSummary
from app.services.llm.client import ChatCompletionClient

_SYSTEM_PROMPT = """You generate beginner-friendly repository learning guides.
Return strict JSON with these keys only:
- mental_model: string
- run_steps: array of 3 to 6 strings
- pitfalls: array of 2 to 5 strings
- self_check_questions: array of 3 to 5 strings
Use concrete repository details. Do not wrap the JSON in markdown fences."""


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

        response = await self._client.complete_json(system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt)
        return TutorialSummary.model_validate(response).model_dump()

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
