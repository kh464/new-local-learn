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


class RepositorySummary(BaseModel):
    name: str
    files: list[str]
    key_files: list[str]
    file_count: int


class DetectedStackSummary(BaseModel):
    frameworks: list[str]
    languages: list[str]


class BackendRouteSummary(BaseModel):
    method: str
    path: str
    source_file: str | None = None


class BackendSummary(BaseModel):
    routes: list[BackendRouteSummary]


class FrontendRouteSummary(BaseModel):
    path: str
    source_file: str | None = None


class FrontendApiCallSummary(BaseModel):
    url: str
    source_file: str | None = None


class FrontendSummary(BaseModel):
    routing: list[FrontendRouteSummary]
    api_calls: list[FrontendApiCallSummary]


class LogicFlowSummary(BaseModel):
    frontend_call: str
    frontend_source: str
    backend_route: str
    backend_source: str
    backend_method: str
    confidence: float


class LogicSummary(BaseModel):
    flows: list[LogicFlowSummary]


class TutorialSummary(BaseModel):
    mental_model: str
    run_steps: list[str]
    pitfalls: list[str]
    self_check_questions: list[str]


class MermaidSections(BaseModel):
    system: str


class AnalysisResult(BaseModel):
    github_url: str
    repo_path: str
    markdown_path: str
    repo_summary: RepositorySummary
    detected_stack: DetectedStackSummary
    backend_summary: BackendSummary
    frontend_summary: FrontendSummary
    logic_summary: LogicSummary
    tutorial_summary: TutorialSummary
    mermaid_sections: MermaidSections
