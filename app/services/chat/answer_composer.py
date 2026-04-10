from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from app.services.chat.models import EvidencePack

_LOGGER = logging.getLogger("app.answer_composer")
_SYSTEM_PROMPT = """你是仓库代码问答的最终回答模型。你必须严格遵守以下规则：
1. 只能使用简体中文回答。
2. 只能基于提供的 evidence_pack、history 和 question 回答。
3. 不允许编造仓库中不存在的文件、函数、调用链、模块、接口或结论。
4. 如果证据不足，必须明确说明证据不足以及还缺什么。
5. 你的 JSON 只能包含：
   - answer: string
   - supplemental_notes: string[]
   - confidence: "high" | "medium" | "low"
6. 你的任务是依据证据生成最终回答，因此必须做到“只能基于证据回答”。"""


class _AnswerPayload(BaseModel):
    answer: str
    supplemental_notes: list[str] = Field(default_factory=list)
    confidence: str = "medium"


class AnswerComposer:
    def __init__(self, *, client=None, max_history_messages: int = 6, max_snippet_chars: int = 800) -> None:
        self._client = client
        self._max_history_messages = max(0, max_history_messages)
        self._max_snippet_chars = max(80, max_snippet_chars)

    async def compose(self, *, question: str, evidence_pack: EvidencePack, history: list) -> dict[str, object]:
        if self._client is not None:
            try:
                payload = await self._client.complete_json(
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=self._build_user_prompt(
                        question=question,
                        evidence_pack=evidence_pack,
                        history=history,
                    ),
                )
                validated = _AnswerPayload.model_validate(payload)
                return {
                    "answer": validated.answer,
                    "supplemental_notes": list(validated.supplemental_notes),
                    "confidence": validated.confidence if validated.confidence in {"high", "medium", "low"} else "medium",
                    "answer_source": "llm",
                }
            except Exception as exc:
                _LOGGER.warning("answer_composer_llm_fallback: %s", exc)

        return self._compose_local(question=question, evidence_pack=evidence_pack)

    def _build_user_prompt(self, *, question: str, evidence_pack: EvidencePack, history: list) -> str:
        payload = {
            "question": question,
            "history": [
                {
                    "role": getattr(message, "role", ""),
                    "content": self._clip_text(getattr(message, "content", ""), 400),
                }
                for message in history[-self._max_history_messages :]
            ],
            "evidence_pack": {
                "question": evidence_pack.question,
                "planning_source": evidence_pack.planning_source,
                "entrypoints": [self._serialize_item(item) for item in evidence_pack.entrypoints],
                "call_chains": [self._serialize_item(item) for item in evidence_pack.call_chains],
                "routes": [self._serialize_item(item) for item in evidence_pack.routes],
                "files": [self._serialize_item(item) for item in evidence_pack.files],
                "symbols": [self._serialize_item(item) for item in evidence_pack.symbols],
                "citations": [self._serialize_item(item) for item in evidence_pack.citations],
                "key_findings": list(evidence_pack.key_findings),
                "reasoning_steps": list(evidence_pack.reasoning_steps),
                "gaps": list(evidence_pack.gaps),
                "confidence_basis": list(evidence_pack.confidence_basis),
            },
        }
        return json.dumps(payload, ensure_ascii=False)

    def _serialize_item(self, item) -> dict[str, object]:
        return {
            "kind": item.kind,
            "path": item.path,
            "title": item.title,
            "summary": self._clip_text(item.summary, 300),
            "start_line": item.start_line,
            "end_line": item.end_line,
            "snippet": self._clip_text(item.snippet, self._max_snippet_chars),
        }

    def _clip_text(self, text: str, limit: int) -> str:
        if limit <= 0 or len(text) <= limit:
            return text
        if limit <= 3:
            return text[:limit]
        return text[: limit - 3] + "..."

    def _compose_local(self, *, question: str, evidence_pack: EvidencePack) -> dict[str, object]:
        if evidence_pack.call_chains:
            chain = evidence_pack.call_chains[0]
            return {
                "answer": f"根据当前仓库证据，最相关的调用链是：{chain.title}。",
                "supplemental_notes": evidence_pack.key_findings[:2],
                "confidence": "high",
                "answer_source": "local",
            }

        if evidence_pack.entrypoints:
            labels = "、".join(item.path or item.title for item in evidence_pack.entrypoints[:2])
            return {
                "answer": f"根据当前仓库证据，我先定位到这些入口位置：{labels}。",
                "supplemental_notes": evidence_pack.key_findings[:2],
                "confidence": "medium",
                "answer_source": "local",
            }

        if evidence_pack.citations:
            labels = "、".join(item.path or item.title for item in evidence_pack.citations[:2])
            return {
                "answer": f"我目前主要命中了这些真实代码位置：{labels}。",
                "supplemental_notes": ["这是基于当前证据的保守回答。"],
                "confidence": "medium",
                "answer_source": "local",
            }

        return {
            "answer": f"我暂时没有从当前证据中得到足够信息来完整回答“{question}”。",
            "supplemental_notes": ["建议继续补充调用链、入口文件或相关代码片段。"],
            "confidence": "low",
            "answer_source": "local",
        }
