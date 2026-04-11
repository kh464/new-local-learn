from __future__ import annotations

import re

from app.services.chat.models import EvidencePack

_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_CODE_ENTITY_PATTERN = re.compile(
    r"[A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|jsx|vue|md|json|yml|yaml|toml)"
    r"|/[A-Za-z0-9_/{}/:-]+"
    r"|\b[A-Z][A-Za-z0-9_]{2,}\b"
    r"|\b[a-z]+_[a-z0-9_]+\b"
)


class AnswerValidator:
    async def validate(
        self,
        *,
        question: str,
        answer: str,
        supplemental_notes: list[str],
        evidence_pack,
    ) -> dict[str, object]:
        issues: list[str] = []
        pack = evidence_pack if isinstance(evidence_pack, EvidencePack) else EvidencePack.model_validate(evidence_pack)

        if answer.strip() and not _CJK_PATTERN.search(answer):
            issues.append("answer_not_chinese")

        if any(note.strip() and not _CJK_PATTERN.search(note) for note in supplemental_notes):
            issues.append("notes_not_chinese")

        if pack.gaps and not self._contains_evidence_disclosure(answer=answer, supplemental_notes=supplemental_notes):
            issues.append("missing_evidence_disclosure")

        allowed_entities = self._collect_allowed_entities(question, pack)
        answer_entities = self._extract_code_entities("\n".join([answer, *supplemental_notes]))
        if any(entity.lower() not in allowed_entities for entity in answer_entities):
            issues.append("ungrounded_entity")

        return {
            "passed": not issues,
            "issues": issues,
            "retryable": "ungrounded_entity" in issues,
            "should_expand_context": False,
            "confidence_override": "low" if issues else None,
        }

    def _collect_allowed_entities(self, question: str, pack: EvidencePack) -> set[str]:
        texts = [question]
        texts.extend(pack.key_findings)
        for group in (
            pack.entrypoints,
            pack.call_chains,
            pack.routes,
            pack.files,
            pack.symbols,
            pack.citations,
        ):
            for item in group:
                texts.extend(filter(None, [item.path, item.title, item.summary, item.snippet]))
        return {entity.lower() for entity in self._extract_code_entities("\n".join(texts))}

    def _extract_code_entities(self, text: str) -> list[str]:
        return list(dict.fromkeys(match.group(0) for match in _CODE_ENTITY_PATTERN.finditer(text)))

    def _contains_evidence_disclosure(self, *, answer: str, supplemental_notes: list[str]) -> bool:
        combined = "\n".join([answer, *supplemental_notes])
        return any(marker in combined for marker in ("证据不足", "当前证据不足", "现有证据不足", "缺少证据", "尚未定位", "尚未命中"))
