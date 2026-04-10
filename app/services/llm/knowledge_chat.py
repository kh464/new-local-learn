from __future__ import annotations

import json
import logging
import re
from pathlib import Path
import inspect

from pydantic import BaseModel, Field

from app.core.models import TaskChatCitation, TaskChatMessage, TaskChatResponse, TaskGraphEvidence
from app.services.knowledge.question_planner import QuestionPlanner
from app.services.knowledge.repo_map_loader import RepoMapLoader
from app.services.knowledge.retriever import KnowledgeRetriever
from app.storage.knowledge_store import KnowledgeSearchResult

_CHAT_LOGGER = logging.getLogger("app.knowledge_chat")
_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_PATH_PATTERN = re.compile(r"(?P<path>[A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|vue|md|json|yml|yaml|toml))")
_CODE_ENTITY_PATTERN = re.compile(
    r"[A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|vue|md|json|yml|yaml|toml)"
    r"|/[A-Za-z0-9_/{}/:-]+"
    r"|\b[A-Z][A-Za-z0-9_]{2,}\b"
    r"|\b[a-z]+_[a-z0-9_]+\b"
)
_SYSTEM_PROMPT = """你是一个面向初学者的代码仓库讲解助手。
你必须严格遵守以下规则：
1. 必须使用简体中文回答。
2. 必须优先参考 graph_evidence 中的仓库结构、入口点和调用链，再结合 citations 中的真实代码片段作答。
3. 不允许编造仓库中不存在的实现、文件、接口、调用关系或结论。
4. 如果证据不足，必须明确说明证据不足，并说明还缺什么。
5. 只能输出 JSON 对象，字段只允许为：
   - answer: string
   - supplemental_notes: string[]
   - confidence: "high" | "medium" | "low"
6. 不要输出 citations 或 graph_evidence 字段，系统会自行附加。"""


class _KnowledgeChatPayload(BaseModel):
    answer: str
    supplemental_notes: list[str] = Field(default_factory=list)
    confidence: str = "medium"


class _OrchestratorKnowledgeChatAdapter:
    def __init__(self, *, orchestrator) -> None:
        self._orchestrator = orchestrator

    async def answer_question(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        repo_map_path: Path | str | None = None,
        question: str,
        history: list[TaskChatMessage],
    ) -> TaskChatResponse:
        return await self._orchestrator.answer_question(
            task_id=task_id,
            db_path=db_path,
            repo_map_path=repo_map_path,
            question=question,
            history=history,
        )


class _TaskScopedOrchestratorKnowledgeChatAdapter:
    def __init__(self, *, orchestrator_factory) -> None:
        self._orchestrator_factory = orchestrator_factory

    async def answer_question(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        repo_map_path: Path | str | None = None,
        question: str,
        history: list[TaskChatMessage],
    ) -> TaskChatResponse:
        orchestrator = self._orchestrator_factory(
            task_id=task_id,
            db_path=db_path,
            repo_map_path=repo_map_path,
            question=question,
            history=history,
        )
        if inspect.isawaitable(orchestrator):
            orchestrator = await orchestrator
        if orchestrator is None:
            raise RuntimeError("Task-scoped orchestrator factory returned no orchestrator.")
        return await orchestrator.answer_question(
            task_id=task_id,
            db_path=db_path,
            repo_map_path=repo_map_path,
            question=question,
            history=history,
        )


class KnowledgeChatService:
    def __init__(
        self,
        *,
        retriever: KnowledgeRetriever | None = None,
        client=None,
        repo_map_loader: RepoMapLoader | None = None,
        max_context_chunks: int = 6,
        max_history_messages: int = 6,
        max_prompt_chars: int = 20_000,
        orchestrator=None,
        orchestrator_factory=None,
        legacy_service=None,
    ) -> None:
        if orchestrator_factory is not None:
            self._delegate = _TaskScopedOrchestratorKnowledgeChatAdapter(
                orchestrator_factory=orchestrator_factory
            )
            return

        if orchestrator is not None:
            self._delegate = _OrchestratorKnowledgeChatAdapter(orchestrator=orchestrator)
            return

        self._delegate = legacy_service or _LegacyKnowledgeChatService(
            retriever=retriever or KnowledgeRetriever(),
            client=client,
            repo_map_loader=repo_map_loader,
            max_context_chunks=max_context_chunks,
            max_history_messages=max_history_messages,
            max_prompt_chars=max_prompt_chars,
        )

    async def answer_question(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        repo_map_path: Path | str | None = None,
        question: str,
        history: list[TaskChatMessage],
    ) -> TaskChatResponse:
        return await self._delegate.answer_question(
            task_id=task_id,
            db_path=db_path,
            repo_map_path=repo_map_path,
            question=question,
            history=history,
        )


class _LegacyKnowledgeChatService:
    def __init__(
        self,
        *,
        retriever: KnowledgeRetriever,
        client=None,
        repo_map_loader: RepoMapLoader | None = None,
        max_context_chunks: int = 6,
        max_history_messages: int = 6,
        max_prompt_chars: int = 20_000,
    ) -> None:
        self._retriever = retriever
        self._client = client
        self._repo_map_loader = repo_map_loader or RepoMapLoader()
        self._max_context_chunks = max(1, max_context_chunks)
        self._max_history_messages = max(0, max_history_messages)
        self._max_prompt_chars = max_prompt_chars

    async def answer_question(
        self,
        *,
        task_id: str,
        db_path: Path | str,
        repo_map_path: Path | str | None = None,
        question: str,
        history: list[TaskChatMessage],
    ) -> TaskChatResponse:
        graph_evidence = self._build_graph_evidence(question, repo_map_path)
        matches = self._retriever.retrieve(
            task_id=task_id,
            db_path=db_path,
            question=self._build_retrieval_question(question, graph_evidence),
            limit=self._max_context_chunks,
        )
        citations = self._build_citations(matches, graph_evidence)

        if self._client is not None and (citations or graph_evidence):
            try:
                payload = await self._client.complete_json(
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=self._build_user_prompt(question, history, graph_evidence, citations),
                )
                validated = _KnowledgeChatPayload.model_validate(payload)
                self._ensure_chinese(validated.answer)
                for note in validated.supplemental_notes:
                    self._ensure_chinese(note)
                self._ensure_grounded_response(
                    question=question,
                    answer=validated.answer,
                    supplemental_notes=validated.supplemental_notes,
                    citations=citations,
                    graph_evidence=graph_evidence,
                )
                return TaskChatResponse(
                    answer=validated.answer,
                    citations=citations,
                    graph_evidence=graph_evidence,
                    supplemental_notes=validated.supplemental_notes,
                    confidence=validated.confidence if validated.confidence in {"high", "medium", "low"} else "medium",
                    answer_source="llm",
                )
            except Exception as exc:
                _CHAT_LOGGER.warning("knowledge_chat_llm_fallback: %s", exc)

        return self._build_fallback_response(question, citations, graph_evidence)

    def _build_citations(
        self,
        matches: list[KnowledgeSearchResult],
        graph_evidence: list[TaskGraphEvidence],
    ) -> list[TaskChatCitation]:
        graph_paths = self._graph_paths(graph_evidence)
        graph_path_order = self._graph_path_order(graph_evidence)
        ranked = sorted(
            matches,
            key=lambda match: self._rank_match(match, graph_paths, graph_path_order),
            reverse=True,
        )

        citations: list[TaskChatCitation] = []
        seen_keys: set[tuple[str, int, int, str]] = set()
        for match in ranked:
            snippet = match.content.strip()
            key = (match.path, match.start_line, match.end_line, snippet)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            citations.append(
                TaskChatCitation(
                    path=match.path,
                    start_line=match.start_line,
                    end_line=match.end_line,
                    reason=self._citation_reason(match.path, graph_paths),
                    snippet=snippet,
                )
            )

        return citations[: min(self._max_context_chunks, 3)]

    def _rank_match(
        self,
        match: KnowledgeSearchResult,
        graph_paths: set[str],
        graph_path_order: dict[str, int],
    ) -> tuple[int, int, float, int, str, int]:
        path_hit = 1 if match.path in graph_paths else 0
        path_priority = -graph_path_order.get(match.path, 999)
        symbol_hit = 1 if (match.symbol_name or "").strip() else 0
        snippet_length = len(match.content.strip())
        return (
            path_hit,
            path_priority,
            -match.score,
            symbol_hit,
            match.path,
            -snippet_length,
        )

    def _citation_reason(self, path: str, graph_paths: set[str]) -> str:
        if path in graph_paths:
            return "这段代码与当前认知图命中的入口、调用链或关键符号直接对应。"
        return "这是知识库检索命中的真实代码片段。"

    def _graph_paths(self, graph_evidence: list[TaskGraphEvidence]) -> set[str]:
        return set(self._iter_graph_paths(graph_evidence))

    def _graph_path_order(self, graph_evidence: list[TaskGraphEvidence]) -> dict[str, int]:
        ordered_paths: dict[str, int] = {}
        for path in self._iter_graph_paths(graph_evidence):
            if path not in ordered_paths:
                ordered_paths[path] = len(ordered_paths)
        return ordered_paths

    def _iter_graph_paths(self, graph_evidence: list[TaskGraphEvidence]) -> list[str]:
        ordered_items = sorted(
            graph_evidence,
            key=lambda item: {
                "call_chain": 0,
                "edge": 1,
                "symbol": 2,
                "entrypoint": 3,
            }.get(item.kind, 4),
        )
        paths: list[str] = []
        for item in ordered_items:
            for text in (item.label, item.detail):
                if not text:
                    continue
                paths.extend(match.group("path") for match in _PATH_PATTERN.finditer(text))
            if item.path:
                paths.append(item.path)
        return paths

    def _build_graph_evidence(self, question: str, repo_map_path: Path | str | None) -> list[TaskGraphEvidence]:
        if repo_map_path is None:
            return []

        path = Path(repo_map_path)
        if not path.is_file():
            return []

        try:
            repo_map = self._repo_map_loader.load(path)
            plan = QuestionPlanner(repo_map).plan(question)
        except Exception as exc:
            _CHAT_LOGGER.warning("repo_map_load_failed: %s", exc)
            return []

        evidence: list[TaskGraphEvidence] = []
        seen: set[tuple[str, str, str | None]] = set()

        for item in plan.entrypoint_hits:
            label = f"{item.get('layer', 'unknown')}入口: {item.get('file_path')}"
            key = ("entrypoint", label, item.get("file_path"))
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                TaskGraphEvidence(
                    kind="entrypoint",
                    label=label,
                    path=str(item.get("file_path") or ""),
                    detail=f"语言: {item.get('language')}",
                )
            )

        for item in plan.call_chain_hits:
            label = str(item.get("summary") or "").strip()
            if not label:
                continue
            key = ("call_chain", label, str(item.get("backend_file") or ""))
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                TaskGraphEvidence(
                    kind="call_chain",
                    label=label,
                    path=str(item.get("backend_file") or item.get("frontend_file") or ""),
                    detail=f"{item.get('method', 'GET')} {item.get('route_path', '')}".strip(),
                )
            )

        for item in plan.symbol_hits[:2]:
            label = str(item.get("name") or "").strip()
            if not label:
                continue
            key = ("symbol", label, str(item.get("file_path") or ""))
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                TaskGraphEvidence(
                    kind="symbol",
                    label=label,
                    path=str(item.get("file_path") or ""),
                    detail=f"{item.get('kind', 'symbol')} @ line {item.get('line', '?')}",
                )
            )

        for item in plan.edge_hits[:2]:
            edge_type = str(item.get("type") or "").strip()
            if not edge_type:
                continue
            label = f"{edge_type}: {item.get('path') or item.get('target') or item.get('backend_file') or ''}".strip()
            key = ("edge", label, str(item.get("backend_file") or item.get("file_path") or ""))
            if key in seen:
                continue
            seen.add(key)
            evidence.append(
                TaskGraphEvidence(
                    kind="edge",
                    label=label,
                    path=str(item.get("backend_file") or item.get("file_path") or ""),
                    detail=f"source={item.get('source')}",
                )
            )

        return evidence[:6]

    def _build_user_prompt(
        self,
        question: str,
        history: list[TaskChatMessage],
        graph_evidence: list[TaskGraphEvidence],
        citations: list[TaskChatCitation],
    ) -> str:
        payload = {
            "question": question,
            "history": [
                {"role": message.role, "content": self._clip_text(message.content, 400)}
                for message in history[-self._max_history_messages :]
            ],
            "graph_evidence": [
                {
                    "kind": item.kind,
                    "label": self._clip_text(item.label, 200),
                    "detail": self._clip_text(item.detail or "", 200) or None,
                    "path": item.path,
                }
                for item in graph_evidence
            ],
            "citations": [
                {
                    "path": citation.path,
                    "start_line": citation.start_line,
                    "end_line": citation.end_line,
                    "reason": self._clip_text(citation.reason, 200),
                    "snippet": self._clip_text(citation.snippet, 400),
                }
                for citation in citations
            ],
        }
        prompt = self._serialize_prompt(payload)
        if len(prompt) <= self._max_prompt_chars:
            return prompt

        reduced = {
            **payload,
            "history": list(payload["history"]),
            "graph_evidence": list(payload["graph_evidence"]),
            "citations": list(payload["citations"]),
        }
        for key in ("history", "citations", "graph_evidence"):
            while reduced[key] and len(self._serialize_prompt(reduced)) > self._max_prompt_chars:
                reduced[key].pop(0)

        prompt = self._serialize_prompt(reduced)
        if len(prompt) <= self._max_prompt_chars:
            return prompt

        minimal = {
            "question": self._clip_text(question, max(self._max_prompt_chars // 2, 16)),
            "history": [],
            "graph_evidence": [],
            "citations": [],
        }
        return self._serialize_prompt(minimal)

    def _serialize_prompt(self, payload: dict[str, object]) -> str:
        return "必须使用简体中文，并且严格基于以下真实证据回答。\n" + json.dumps(payload, ensure_ascii=False)

    def _clip_text(self, text: str, limit: int) -> str:
        if limit <= 0 or len(text) <= limit:
            return text
        if limit <= 3:
            return text[:limit]
        return text[: limit - 3] + "..."

    def _build_retrieval_question(self, question: str, graph_evidence: list[TaskGraphEvidence]) -> str:
        hints: list[str] = []
        for item in graph_evidence[:4]:
            if item.path:
                hints.append(item.path)
            if item.label:
                hints.append(item.label)
        if not hints:
            return question
        return f"{question}\n" + "\n".join(dict.fromkeys(hints))

    def _build_fallback_response(
        self,
        question: str,
        citations: list[TaskChatCitation],
        graph_evidence: list[TaskGraphEvidence],
    ) -> TaskChatResponse:
        answer_parts: list[str] = []

        if graph_evidence:
            call_chain = next((item for item in graph_evidence if item.kind == "call_chain"), None)
            if call_chain is not None:
                answer_parts.append(self._describe_call_chain(call_chain))
            else:
                answer_parts.append(f"根据当前仓库认知图，我先定位到了这些关键结构：{self._join_labels(graph_evidence[:3])}。")

        if citations:
            paths = "、".join(citation.path for citation in citations[:3])
            answer_parts.append(f"对应的真实代码证据主要落在 {paths}。")
            confidence = "medium"
        else:
            answer_parts.append(f"我暂时没有从当前代码知识库中检索到足够直接的证据来完整回答“{question}”。")
            confidence = "low"

        notes = ["这是降级回答，优先依据当前知识库命中的真实代码片段和仓库认知图生成。"]
        if not graph_evidence and not citations:
            notes.append("建议你换一个更具体的文件名、函数名、接口路径或问题范围再问一次。")

        return TaskChatResponse(
            answer="".join(answer_parts),
            citations=citations,
            graph_evidence=graph_evidence,
            supplemental_notes=notes,
            confidence=confidence,
            answer_source="local",
        )

    def _join_labels(self, graph_evidence: list[TaskGraphEvidence]) -> str:
        return "、".join(item.label for item in graph_evidence if item.label)

    def _describe_call_chain(self, call_chain: TaskGraphEvidence) -> str:
        segments = [segment.strip() for segment in call_chain.label.split("->") if segment.strip()]
        route_index = self._find_route_segment_index(segments)
        if route_index is not None and route_index >= 1 and route_index + 1 < len(segments):
            frontend_segments = segments[:route_index]
            route_segment = segments[route_index]
            backend_segments = segments[route_index + 1 :]
            handler_segment = frontend_segments[-1]
            frontend_summary = self._describe_frontend_flow(frontend_segments)
            answer = (
                f"根据当前仓库认知图，请求会先从 {handler_segment} 发起，再经过 {route_segment}，再进入 {backend_segments[0]}。"
                f"{frontend_summary}接口路由 {route_segment}，后端处理位置 {backend_segments[0]}。"
            )
            if len(backend_segments) > 1:
                answer += f"后续还会调用 {'、'.join(backend_segments[1:])}。"
            return answer
        return f"根据当前仓库认知图，这个问题的主要调用链是：{call_chain.label}。"

    def _ensure_chinese(self, text: str) -> None:
        if text.strip() and not _CJK_PATTERN.search(text):
            raise ValueError("Knowledge chat output must be Chinese.")

    def _ensure_grounded_response(
        self,
        *,
        question: str,
        answer: str,
        supplemental_notes: list[str],
        citations: list[TaskChatCitation],
        graph_evidence: list[TaskGraphEvidence],
    ) -> None:
        allowed_entities = self._collect_allowed_entities(question, citations, graph_evidence)
        answer_entities = self._extract_code_entities("\n".join([answer, *supplemental_notes]))
        unsupported = [entity for entity in answer_entities if entity.lower() not in allowed_entities]
        if unsupported:
            raise ValueError(f"Knowledge chat output referenced unsupported entities: {', '.join(unsupported[:5])}")

    def _collect_allowed_entities(
        self,
        question: str,
        citations: list[TaskChatCitation],
        graph_evidence: list[TaskGraphEvidence],
    ) -> set[str]:
        texts = [question]
        texts.extend(citation.path for citation in citations)
        texts.extend(citation.snippet for citation in citations)
        texts.extend(citation.reason for citation in citations)
        for item in graph_evidence:
            texts.extend(filter(None, [item.label, item.detail, item.path]))
        return {entity.lower() for entity in self._extract_code_entities("\n".join(texts))}

    def _extract_code_entities(self, text: str) -> list[str]:
        return list(dict.fromkeys(match.group(0) for match in _CODE_ENTITY_PATTERN.finditer(text)))

    def _describe_frontend_segment(self, segment: str) -> str:
        match = re.match(r"(?P<target>.+?):(?P<handler>[A-Za-z_][A-Za-z0-9_]*)(?: \[(?P<trigger>[^\]]+)\])?$", segment)
        if match is None:
            return f"前端文件 {segment}"
        target = match.group("target")
        handler = match.group("handler")
        trigger = match.group("trigger")
        if trigger:
            return f"前端入口函数 {target}:{handler}，由 {trigger} 交互触发"
        return f"前端入口函数 {target}:{handler}"

    def _describe_frontend_flow(self, frontend_segments: list[str]) -> str:
        if not frontend_segments:
            return ""

        handler_match = re.match(
            r"(?P<target>.+?):(?P<handler>[A-Za-z_][A-Za-z0-9_]*)(?: \[(?P<trigger>[^\]]+)\])?$",
            frontend_segments[-1],
        )

        parts: list[str] = []
        if len(frontend_segments) >= 2:
            parts.append(f"页面入口 {frontend_segments[0]}。")

        component_chain: list[str] = []
        if len(frontend_segments) >= 3:
            component_chain.extend(frontend_segments[1:-1])
        if handler_match is not None and len(frontend_segments) >= 2:
            component_chain.append(str(handler_match.group("target")))
        if component_chain:
            deduped_chain = list(dict.fromkeys(component_chain))
            parts.append(f"组件挂载链 {' -> '.join(deduped_chain)}。")

        if handler_match is not None:
            target = str(handler_match.group("target"))
            handler = str(handler_match.group("handler"))
            trigger = handler_match.group("trigger")
            if trigger:
                parts.append(f"前端入口函数 {target}:{handler}，由 {trigger} 交互触发。")
            else:
                parts.append(f"前端入口函数 {target}:{handler}。")
        else:
            parts.append(f"前端文件 {frontend_segments[-1]}。")

        return "".join(parts)

    def _find_route_segment_index(self, segments: list[str]) -> int | None:
        for index, segment in enumerate(segments):
            if re.match(r"^(GET|POST|PUT|DELETE|PATCH)\s+/", segment):
                return index
        return None
