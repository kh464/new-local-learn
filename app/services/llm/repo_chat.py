from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.models import AnalysisResult, TaskChatCitation, TaskChatMessage, TaskChatResponse

_CHAT_LOGGER = logging.getLogger("app.repo_chat")
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_SYSTEM_PROMPT = """你是一个面向初学者的仓库学习助手。你必须严格返回 JSON 对象，并且只能包含以下字段：
- answer: string
- citations: array
- supplemental_notes: array
- confidence: string

硬性要求：
1. 必须使用简体中文回答。
2. 回答优先基于当前仓库证据，不允许编造仓库中不存在的实现。
3. citations 至少包含 1 个引用，每个引用必须包含 path、start_line、end_line、reason、snippet。
4. 允许补充少量通用知识，但必须放到 supplemental_notes 中，不能和仓库事实混写。
5. 如果证据不足，要明确说明证据不足，不能假装确定。
"""


@dataclass
class _CandidateContext:
    path: str
    reason: str
    search_terms: list[str]
    score: int


class RepositoryChatService:
    def __init__(
        self,
        client=None,
        *,
        max_context_files: int = 4,
        max_history_messages: int = 6,
        max_prompt_chars: int = 20000,
        max_snippet_lines: int = 24,
    ) -> None:
        self._client = client
        self._max_context_files = max_context_files
        self._max_history_messages = max_history_messages
        self._max_prompt_chars = max_prompt_chars
        self._max_snippet_lines = max_snippet_lines

    async def answer_question(
        self,
        *,
        question: str,
        result: AnalysisResult,
        history: list[TaskChatMessage],
    ) -> TaskChatResponse:
        context = self._build_context(question, result)
        if self._client is not None:
            try:
                payload = await self._client.complete_json(
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=self._build_user_prompt(question, result, history, context),
                )
                response = TaskChatResponse.model_validate(payload)
                self._ensure_chinese_response(response)
                self._ensure_citations(response)
                return response
            except Exception as exc:
                _CHAT_LOGGER.warning("repo_chat_llm_fallback: %s", exc)

        return self._build_fallback_response(question, context)

    def _build_user_prompt(
        self,
        question: str,
        result: AnalysisResult,
        history: list[TaskChatMessage],
        context: list[TaskChatCitation],
    ) -> str:
        history_payload = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in history[-self._max_history_messages :]
        ]
        payload = {
            "question": question,
            "history": history_payload,
            "repo_summary": {
                "name": result.repo_summary.name,
                "github_url": result.github_url,
                "frameworks": result.detected_stack.frameworks,
                "languages": result.detected_stack.languages,
                "backend_routes": [
                    {
                        "method": route.method,
                        "path": route.path,
                        "source_file": route.source_file,
                    }
                    for route in result.backend_summary.routes
                ],
                "frontend_components": [
                    {
                        "name": component.name,
                        "source_file": component.source_file,
                    }
                    for component in result.frontend_summary.components
                ],
                "frontend_api_calls": [
                    {
                        "url": call.url,
                        "method": call.method,
                        "source_file": call.source_file,
                    }
                    for call in result.frontend_summary.api_calls
                ],
                "logic_flows": [
                    {
                        "frontend_call": flow.frontend_call,
                        "frontend_source": flow.frontend_source,
                        "backend_route": flow.backend_route,
                        "backend_source": flow.backend_source,
                    }
                    for flow in result.logic_summary.flows
                ],
            },
            "context_files": [citation.model_dump() for citation in context],
        }
        prompt = "必须使用简体中文回答，并区分仓库事实与补充说明。\n" + json.dumps(payload, ensure_ascii=False)
        return prompt[: self._max_prompt_chars]

    def _build_context(self, question: str, result: AnalysisResult) -> list[TaskChatCitation]:
        candidates = self._rank_candidates(question, result)
        citations: list[TaskChatCitation] = []
        for candidate in candidates[: self._max_context_files]:
            citation = self._load_citation(result.repo_path, candidate)
            if citation is not None:
                citations.append(citation)
        if citations:
            return citations

        for path in result.repo_summary.key_files[: self._max_context_files]:
            fallback = self._load_citation(
                result.repo_path,
                _CandidateContext(
                    path=path,
                    reason="这是仓库的关键入口文件。",
                    search_terms=[],
                    score=0,
                ),
            )
            if fallback is not None:
                citations.append(fallback)
        return citations

    def _rank_candidates(self, question: str, result: AnalysisResult) -> list[_CandidateContext]:
        lowered_question = question.lower()
        seen: set[str] = set()
        candidates: list[_CandidateContext] = []

        def add_candidate(path: str | None, reason: str, search_terms: list[str], *, group: str) -> None:
            if not path or path in seen:
                return
            seen.add(path)
            score = 0
            basename = Path(path).name.lower()
            if basename and basename in lowered_question:
                score += 5
            for term in search_terms:
                normalized = term.lower().strip()
                if normalized and normalized in lowered_question:
                    score += 3
            if group == "backend" and any(keyword in question for keyword in ("后端", "接口", "路由", "服务", "入口")):
                score += 2
            if group == "frontend" and any(keyword in question for keyword in ("前端", "页面", "组件", "界面", "调用")):
                score += 2
            if group == "deploy" and any(keyword in question.lower() for keyword in ("部署", "docker", "k8s", "环境", "redis")):
                score += 2
            if group == "logic" and any(keyword in question for keyword in ("流程", "链路", "调用", "请求")):
                score += 2
            candidates.append(_CandidateContext(path=path, reason=reason, search_terms=search_terms, score=score))

        for route in result.backend_summary.routes:
            add_candidate(
                route.source_file,
                f"这里定义了后端路由 {route.method} {route.path}。",
                [route.method, route.path],
                group="backend",
            )
        for route in result.frontend_summary.routing:
            add_candidate(
                route.source_file,
                f"这里定义了前端路由 {route.path}。",
                [route.path],
                group="frontend",
            )
        for call in result.frontend_summary.api_calls:
            add_candidate(
                call.source_file,
                f"这里发起了前端接口调用 {call.method or ''} {call.url}。",
                [call.url, call.method or "", call.client or ""],
                group="frontend",
            )
        for component in result.frontend_summary.components:
            add_candidate(
                component.source_file,
                f"这里定义了组件 {component.name}。",
                [component.name, *component.imports],
                group="frontend",
            )
        for unit in result.frontend_summary.state_units:
            add_candidate(
                unit.source_file,
                f"这里定义了状态单元 {unit.name}。",
                [unit.name, unit.kind],
                group="frontend",
            )
        for flow in result.logic_summary.flows:
            add_candidate(
                flow.frontend_source,
                f"这里包含前端调用 {flow.frontend_call}。",
                [flow.frontend_call, flow.backend_route],
                group="logic",
            )
            add_candidate(
                flow.backend_source,
                f"这里承接了后端路由 {flow.backend_method} {flow.backend_route}。",
                [flow.backend_route, flow.backend_method],
                group="logic",
            )
        for walkthrough in result.tutorial_summary.code_walkthroughs:
            add_candidate(
                walkthrough.source_file,
                f"教程代码走读引用了 {walkthrough.title}。",
                [walkthrough.title, walkthrough.snippet],
                group="logic",
            )
        for service in result.deploy_summary.services:
            add_candidate(
                service.source_file,
                f"这里定义了部署服务 {service.name}。",
                [service.name, *service.ports, *service.depends_on],
                group="deploy",
            )
        for path in result.deploy_summary.environment_files + result.deploy_summary.manifests + result.repo_summary.key_files:
            add_candidate(
                path,
                "这是仓库的关键配置文件。",
                [Path(path).name],
                group="deploy" if any(marker in path.lower() for marker in ("docker", "k8s", ".env", "compose")) else "logic",
            )

        return sorted(candidates, key=lambda item: (-item.score, item.path))

    def _load_citation(self, repo_path: str, candidate: _CandidateContext) -> TaskChatCitation | None:
        file_path = Path(repo_path) / candidate.path
        if not file_path.is_file():
            return None
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

        lines = content.splitlines() or [content]
        start_index = 0
        for index, line in enumerate(lines):
            lowered_line = line.lower()
            if any(term.lower().strip() and term.lower().strip() in lowered_line for term in candidate.search_terms):
                start_index = index
                break
        end_index = min(len(lines), start_index + self._max_snippet_lines)
        snippet = "\n".join(lines[start_index:end_index]).strip()
        if not snippet:
            snippet = "\n".join(lines[: self._max_snippet_lines]).strip()
            start_index = 0
            end_index = min(len(lines), self._max_snippet_lines)
        return TaskChatCitation(
            path=candidate.path,
            start_line=start_index + 1,
            end_line=max(start_index + 1, end_index),
            reason=candidate.reason,
            snippet=snippet,
        )

    def _build_fallback_response(self, question: str, context: list[TaskChatCitation]) -> TaskChatResponse:
        if context:
            paths = "、".join(citation.path for citation in context[:3])
            answer = (
                f"根据当前仓库，和“{question}”最相关的实现主要在 {paths}。"
                "你可以先从这些文件入手，我已经把最相关的代码片段附在引用里。"
            )
        else:
            answer = (
                f"我暂时没有从当前仓库中检索到足够直接的证据来完整回答“{question}”。"
                "建议先从关键入口文件继续排查。"
            )
        return TaskChatResponse(
            answer=answer,
            citations=context,
            supplemental_notes=["这是降级回答，优先依据当前仓库摘要和命中文件生成。"],
            confidence="medium" if context else "low",
        )

    def _ensure_chinese_response(self, response: TaskChatResponse) -> None:
        text_fields = [response.answer, *response.supplemental_notes]
        for text in text_fields:
            if text.strip() and not _CJK_PATTERN.search(text):
                raise ValueError("Repository chat output must be Chinese.")

    def _ensure_citations(self, response: TaskChatResponse) -> None:
        if not response.citations:
            raise ValueError("Repository chat output must include citations.")
