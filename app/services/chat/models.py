from __future__ import annotations

from pydantic import AliasChoices, BaseModel, Field


class AgentToolCall(BaseModel):
    name: str = Field(validation_alias=AliasChoices("name", "tool_name"))
    arguments: dict[str, object] = Field(default_factory=dict)
    reason: str = ""


class AgentObservation(BaseModel):
    tool_name: str
    success: bool
    summary: str
    payload: dict[str, object] = Field(default_factory=dict)


class PlannerResult(BaseModel):
    inferred_intent: str
    answer_depth: str
    current_hypothesis: str
    gaps: list[str] = Field(default_factory=list)
    ready_to_answer: bool = False
    tool_call: AgentToolCall | None = None


class EvidenceItem(BaseModel):
    kind: str
    path: str = ""
    title: str
    summary: str = ""
    start_line: int | None = None
    end_line: int | None = None
    snippet: str = ""


class EvidencePack(BaseModel):
    question: str
    planning_source: str
    entrypoints: list[EvidenceItem] = Field(default_factory=list)
    call_chains: list[EvidenceItem] = Field(default_factory=list)
    routes: list[EvidenceItem] = Field(default_factory=list)
    files: list[EvidenceItem] = Field(default_factory=list)
    symbols: list[EvidenceItem] = Field(default_factory=list)
    citations: list[EvidenceItem] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    reasoning_steps: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    confidence_basis: list[str] = Field(default_factory=list)
