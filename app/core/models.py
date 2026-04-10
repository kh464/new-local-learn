from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from app.core.chat_models import PlannerMetadata
from pydantic import BaseModel, Field, HttpUrl, field_validator


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
    BUILD_KNOWLEDGE = "build_knowledge"
    FINALIZE = "finalize"


class TaskKnowledgeState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class AnalyzeRequest(BaseModel):
    github_url: HttpUrl


class TaskStatus(BaseModel):
    task_id: str
    state: TaskState
    stage: TaskStage | None = None
    progress: int = Field(default=0, ge=0, le=100)
    message: str | None = None
    error: str | None = None
    knowledge_state: TaskKnowledgeState = TaskKnowledgeState.PENDING
    knowledge_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskChatCitation(BaseModel):
    path: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    reason: str
    snippet: str


class TaskGraphEvidence(BaseModel):
    kind: Literal["entrypoint", "symbol", "edge", "call_chain"]
    label: str
    detail: str | None = None
    path: str | None = None


class TaskChatMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    citations: list[TaskChatCitation] = Field(default_factory=list)
    graph_evidence: list[TaskGraphEvidence] = Field(default_factory=list)
    supplemental_notes: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] | None = None
    answer_source: Literal["llm", "local"] | None = None
    planner_metadata: PlannerMetadata | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator("question")
    @classmethod
    def _normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question must not be blank.")
        return normalized


class TaskChatResponse(BaseModel):
    answer: str
    citations: list[TaskChatCitation] = Field(default_factory=list)
    graph_evidence: list[TaskGraphEvidence] = Field(default_factory=list)
    supplemental_notes: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    answer_source: Literal["llm", "local"] = "local"
    planner_metadata: PlannerMetadata | None = None


class TaskChatExchange(BaseModel):
    task_id: str
    user_message: TaskChatMessage
    assistant_message: TaskChatMessage


class TaskChatHistory(BaseModel):
    task_id: str
    messages: list[TaskChatMessage] = Field(default_factory=list)


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
