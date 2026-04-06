from enum import Enum

from pydantic import BaseModel, Field


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskStage(str, Enum):
    FETCH_REPO = "fetch_repo"
    ANALYZE_REPO = "analyze_repo"
    GENERATE_DOCS = "generate_docs"
    COMPLETE = "complete"


class AnalyzeRequest(BaseModel):
    repo_url: str
    github_token: str | None = None


class TaskStatus(BaseModel):
    task_id: str
    state: TaskState
    stage: TaskStage
    progress: int = Field(default=0, ge=0, le=100)
    message: str | None = None
