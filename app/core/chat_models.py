from pydantic import BaseModel, Field


class PlannerMetadata(BaseModel):
    planning_source: str
    loop_count: int = 0
    used_tools: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    search_queries: list[str] = Field(default_factory=list)
    question_type: str | None = None
    retrieval_objective: str | None = None
    must_include_entities: list[str] = Field(default_factory=list)
    preferred_evidence_kinds: list[str] = Field(default_factory=list)
