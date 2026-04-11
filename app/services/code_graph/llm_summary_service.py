from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.services.code_graph.summary_prompts import FILE_SUMMARY_SYSTEM_PROMPT, SYMBOL_SUMMARY_SYSTEM_PROMPT


class FileSummaryPayload(BaseModel):
    summary_zh: str
    responsibility_zh: str = ""
    upstream_zh: str = ""
    downstream_zh: str = ""
    keywords_zh: list[str] = Field(default_factory=list)
    summary_confidence: str = "medium"


class SymbolSummaryPayload(BaseModel):
    summary_zh: str
    input_output_zh: str = ""
    side_effects_zh: str = ""
    call_targets_zh: str = ""
    callers_zh: str = ""
    summary_confidence: str = "medium"


class LlmSummaryService:
    def __init__(self, *, client) -> None:
        self._client = client

    async def generate_file_summary(
        self,
        *,
        file_path: str,
        language: str,
        evidence: dict[str, object],
    ) -> FileSummaryPayload:
        payload = await self._client.complete_json(
            system_prompt=FILE_SUMMARY_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "file_path": file_path,
                    "language": language,
                    "evidence": evidence,
                },
                ensure_ascii=False,
            ),
        )
        return FileSummaryPayload.model_validate(payload)

    async def generate_symbol_summary(
        self,
        *,
        symbol_name: str,
        symbol_kind: str,
        file_path: str,
        language: str,
        evidence: dict[str, object],
    ) -> SymbolSummaryPayload:
        payload = await self._client.complete_json(
            system_prompt=SYMBOL_SUMMARY_SYSTEM_PROMPT,
            user_prompt=json.dumps(
                {
                    "symbol_name": symbol_name,
                    "symbol_kind": symbol_kind,
                    "file_path": file_path,
                    "language": language,
                    "evidence": evidence,
                },
                ensure_ascii=False,
            ),
        )
        return SymbolSummaryPayload.model_validate(payload)
