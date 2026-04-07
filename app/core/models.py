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


class TaskListItem(TaskStatus):
    github_url: str | None = None


class TaskListPage(BaseModel):
    tasks: list[TaskListItem] = Field(default_factory=list)
    total: int = 0
    limit: int = Field(default=25, ge=0)
    offset: int = Field(default=0, ge=0)


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
    client: str | None = None
    method: str | None = None


class FrontendStateUnitSummary(BaseModel):
    name: str
    kind: str
    source_file: str


class FrontendComponentSummary(BaseModel):
    name: str
    source_file: str
    imports: list[str] = Field(default_factory=list)


class FrontendSummary(BaseModel):
    framework: str | None = None
    bundler: str | None = None
    state_manager: str | None = None
    routing: list[FrontendRouteSummary] = Field(default_factory=list)
    api_calls: list[FrontendApiCallSummary] = Field(default_factory=list)
    state_units: list[FrontendStateUnitSummary] = Field(default_factory=list)
    components: list[FrontendComponentSummary] = Field(default_factory=list)


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
    request_lifecycle: list[str] = Field(default_factory=list)
    run_steps: list[str] = Field(default_factory=list)
    pitfalls: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    self_check_questions: list[str] = Field(default_factory=list)
    faq_entries: list["TutorialFaqEntry"] = Field(default_factory=list)
    code_walkthroughs: list["TutorialCodeWalkthrough"] = Field(default_factory=list)


class TutorialFaqEntry(BaseModel):
    question: str
    answer: str


class TutorialCodeWalkthrough(BaseModel):
    title: str
    source_file: str
    snippet: str
    notes: list[str] = Field(default_factory=list)


class DeployServiceSummary(BaseModel):
    name: str
    source_file: str
    ports: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class EnvironmentVariableSummary(BaseModel):
    key: str
    source_file: str


class KubernetesResourceSummary(BaseModel):
    kind: str
    name: str
    source_file: str


class DeploySummary(BaseModel):
    services: list[DeployServiceSummary] = Field(default_factory=list)
    environment_files: list[str] = Field(default_factory=list)
    manifests: list[str] = Field(default_factory=list)
    environment_variables: list[EnvironmentVariableSummary] = Field(default_factory=list)
    kubernetes_resources: list[KubernetesResourceSummary] = Field(default_factory=list)


class CritiqueSummary(BaseModel):
    coverage_notes: list[str] = Field(default_factory=list)
    inferred_sections: list[str] = Field(default_factory=list)
    missing_areas: list[str] = Field(default_factory=list)


class AgentExecutionNode(BaseModel):
    node: str
    stage: str
    kind: str
    status: str
    depends_on: list[str] = Field(default_factory=list)
    execution_mode: str | None = None
    reason: str | None = None


class AgentMetadata(BaseModel):
    enabled: bool
    used_roles: list[str] = Field(default_factory=list)
    fallbacks: list[str] = Field(default_factory=list)
    execution_nodes: list[AgentExecutionNode] = Field(default_factory=list)


class MermaidSections(BaseModel):
    system: str


class AnalysisResult(BaseModel):
    github_url: str
    repo_path: str
    markdown_path: str
    html_path: str
    pdf_path: str
    repo_summary: RepositorySummary
    detected_stack: DetectedStackSummary
    backend_summary: BackendSummary
    frontend_summary: FrontendSummary
    deploy_summary: DeploySummary = Field(default_factory=DeploySummary)
    logic_summary: LogicSummary
    tutorial_summary: TutorialSummary
    critique_summary: CritiqueSummary = Field(default_factory=CritiqueSummary)
    mermaid_sections: MermaidSections
    agent_metadata: AgentMetadata | None = None
