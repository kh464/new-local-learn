from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl


class TaskState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStage(str, Enum):
    FETCH_REPO = "fetch_repo"
    SCAN_TREE = "scan_tree"
    DETECT_STACK = "detect_stack"
    ANALYZE_BACKEND = "analyze_backend"
    ANALYZE_FRONTEND = "analyze_frontend"
    BUILD_DOC = "build_doc"
    FINALIZE = "finalize"


class AnalyzeRequest(BaseModel):
    github_url: HttpUrl


class TaskStatus(BaseModel):
    task_id: str
    state: TaskState
    stage: TaskStage | None = None
    progress: int = Field(default=0, ge=0, le=100)
    message: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AnalysisResult(BaseModel):
    github_url: str
    repo_path: str
    markdown_path: str
    detected_stack: dict[str, list[str]]
