from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from app.services.chat.models import EvidencePack

_LOGGER = logging.getLogger("app.answer_composer")
_SYSTEM_PROMPT = """你是仓库代码问答系统的最终回答模型。

你的唯一任务，是基于已经收集到的真实证据生成最终回答。你必须严格遵守以下规则：

1. 只能使用简体中文回答。
2. 只能基于提供的 question、history 和 evidence_pack 回答，不允许使用外部常识补全仓库事实。
3. 不允许编造仓库中不存在的文件、函数、类、接口、配置项、调用链或结论。
4. 先直接回答用户问题，再补充必要说明，不要先说套话。
5. 必须区分“已确认事实”和“推断”：
   - 已确认事实：必须能被 evidence_pack 中的真实证据直接支撑。
   - 推断：只有在证据能支撑方向但不能完全下结论时才能使用，并明确写出“这是基于现有证据的推断”。
6. 如果证据不足，必须明确说明“证据不足”，并指出还缺什么证据，不要伪装成完整回答。
7. 如果 evidence_pack 中存在 citations、call_chains、files、symbols、routes、entrypoints，请优先利用这些证据组织回答。
8. supplemental_notes 只能写必要补充，不要重复主答案。
9. 你的 JSON 只能包含：
   - answer: string
   - supplemental_notes: string[]
   - confidence: "high" | "medium" | "low"

你必须做到“只能基于证据回答”。"""


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
            "answer_contract": {
                "language": "zh-CN",
                "answer_style": "先直接回答用户问题，再给必要说明",
                "must_ground_in_evidence": True,
                "must_distinguish_fact_and_inference": True,
                "if_insufficient_evidence": "明确说明证据不足，并指出缺失证据",
            },
            "evidence_pack": {
                "question": evidence_pack.question,
                "planning_source": evidence_pack.planning_source,
                "entrypoints": [self._serialize_item(item) for item in evidence_pack.entrypoints],
                "call_chains": [self._serialize_item(item) for item in evidence_pack.call_chains],
                "routes": [self._serialize_item(item) for item in evidence_pack.routes],
                "files": [self._serialize_item(item) for item in evidence_pack.files],
                "symbols": [self._serialize_item(item) for item in evidence_pack.symbols],
                "citations": [self._serialize_item(item) for item in evidence_pack.citations],
                "confirmed_facts": list(evidence_pack.key_findings),
                "reasoning_steps": list(evidence_pack.reasoning_steps),
                "inferences": self._build_inferences(evidence_pack),
                "evidence_gaps": list(evidence_pack.gaps),
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

    def _build_inferences(self, evidence_pack: EvidencePack) -> list[str]:
        inferences: list[str] = []
        if evidence_pack.call_chains and evidence_pack.citations:
            inferences.append("调用链与代码片段相互印证，回答可以直接围绕已确认链路展开。")
        elif evidence_pack.citations and not evidence_pack.call_chains:
            inferences.append("当前主要命中了代码片段，但调用链信息仍不完整。")
        elif evidence_pack.files or evidence_pack.symbols:
            inferences.append("当前主要命中了文件或符号级证据，需要谨慎回答。")
        return inferences

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
                "supplemental_notes": self._build_local_notes(evidence_pack, fallback_limit=2),
                "confidence": "high" if evidence_pack.citations else "medium",
                "answer_source": "local",
            }

        if evidence_pack.entrypoints:
            labels = "、".join(item.path or item.title for item in evidence_pack.entrypoints[:2])
            return {
                "answer": f"根据当前仓库证据，我先定位到这些入口位置：{labels}。",
                "supplemental_notes": self._build_local_notes(evidence_pack, fallback_limit=2),
                "confidence": "medium",
                "answer_source": "local",
            }

        if evidence_pack.citations:
            labels = "、".join(item.path or item.title for item in evidence_pack.citations[:2])
            return {
                "answer": f"我目前主要命中了这些真实代码位置：{labels}。",
                "supplemental_notes": self._build_local_notes(
                    evidence_pack,
                    defaults=["这是基于当前证据的保守回答。"],
                    fallback_limit=2,
                ),
                "confidence": "medium",
                "answer_source": "local",
            }

        gaps = list(evidence_pack.gaps)
        if gaps:
            return {
                "answer": f"关于“{question}”，当前证据不足，暂时不能给出可靠结论。",
                "supplemental_notes": gaps[:3],
                "confidence": "low",
                "answer_source": "local",
            }

        return {
            "answer": f"关于“{question}”，我暂时没有从当前证据中得到足够信息来完整回答，当前证据不足。",
            "supplemental_notes": ["建议继续补充调用链、入口文件或相关代码片段。"],
            "confidence": "low",
            "answer_source": "local",
        }

    def _build_local_notes(
        self,
        evidence_pack: EvidencePack,
        *,
        defaults: list[str] | None = None,
        fallback_limit: int = 2,
    ) -> list[str]:
        notes = list(evidence_pack.key_findings[:fallback_limit])
        if not notes and defaults:
            notes.extend(defaults)
        if evidence_pack.gaps:
            notes.extend(evidence_pack.gaps[: max(0, 3 - len(notes))])
        return notes[:3]
