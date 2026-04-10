from pydantic import BaseModel, Field


class PlannerMetadata(BaseModel):
    planning_source: str
    loop_count: int = 0
    used_tools: list[str] = Field(default_factory=list)
    fallback_used: bool = False
